import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import io
import traceback
import os
import hashlib

load_dotenv()

# ===========================
# CONFIGURATION
# ===========================
TOKEN = str(os.getenv("DISCORD_TOKEN"))  # Remplace par le token du bot
SHEET_PATH = str(os.getenv("EDT_PATH"))  # URL du CSV exporté depuis Google Sheets

# Dictionnaire de correspondance codes -> intitulés
MATIERE_MAP = {
    "UTC501": "Maths",
    "UTC502": "OS",
    "UTC503": "Programmation",
    "UTC504 - IM": "SI et BD",
    "UTC505": "Réseaux",
    "GDN100": "Gestion",
    "SEC102-FC": "Cybersécurité",
    "SEC102-AD": "Cybersécurité",
    "NFP121": "Programmation avancée",
    "NFP107": "SQL",
    "RSX102": "Applications réseaux",
    "ANG320": "Anglais",
}

MOIS_MAPPING = {
    "january": "JANVIER", "february": "FÉVRIER", "march": "MARS",
    "april": "AVRIL", "may": "MAI", "june": "JUIN",
    "july": "JUILLET", "august": "AOÛT", "september": "SEPTEMBRE",
    "october": "OCTOBRE", "november": "NOVEMBRE", "december": "DECEMBRE"
}


# ===========================
# BOT SETUP
# ===========================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)


# Fonction pour transformer le code en "CODE : Intitulé"
def remplacer_code_matiere(code):
    if pd.isna(code):
        return ""
    code = str(code).strip()

    if code in MATIERE_MAP:
        return f"{code} : {MATIERE_MAP[code]}"
    if code.startswith("SEM"):
        return ""  # traiter les NaN comme des cellules vides
    return code  # si code inconnu, garder tel quel


matiere_colors = {}


def generer_couleur_automatique(code):
    """Génère une couleur hexadécimale pastel unique basée sur le code de l'UE"""
    code = str(code).strip()
    # Créer un hash du code
    hash_obj = hashlib.md5(code.encode())
    hash_hex = hash_obj.hexdigest()

    # Extraire les composantes RGB du hash
    r = int(hash_hex[0:2], 16)
    g = int(hash_hex[2:4], 16)
    b = int(hash_hex[4:6], 16)

    # Convertir en pastel : augmenter la luminosité en mélangeant avec du blanc
    # Formule : couleur_pastel = couleur * 0.5 + blanc * 0.5
    r = int(r * 0.5 + 255 * 0.5)
    g = int(g * 0.5 + 255 * 0.5)
    b = int(b * 0.5 + 255 * 0.5)

    return f"#{r:02x}{g:02x}{b:02x}"


def couleur_matiere(code):
    if code is None:
        return "#FFFFFF"  # blanc par défaut
    code_seul = str(code).split(" :")[0].strip()  # récupérer le code seul
    # Essayer d'abord le dictionnaire, sinon générer automatiquement
    return matiere_colors.get(code_seul, generer_couleur_automatique(code_seul))


def couleur_texte(couleur_hex):
    """Détermine si le texte doit être blanc ou noir selon la luminosité du fond"""
    # Convertir hex en RGB
    couleur_hex = couleur_hex.lstrip('#')
    r, g, b = tuple(int(couleur_hex[i:i + 2], 16) for i in (0, 2, 4))

    # Calculer la luminosité (formule standard)
    luminosite = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    # Si luminosité < 0.5, fond sombre -> texte blanc
    return "#FFFFFF" if luminosite < 0.5 else "#000000"


def parse_iso_date(s: str):
    # Attend "YYYY-MM-DD"
    return datetime.strptime(s, "%d-%m-%Y").date()


def find_month_col_index(df: pd.DataFrame, mois_cle: str):
    header_row = df.iloc[0].astype(str)
    for i, val in enumerate(header_row):
        if pd.notna(val) and mois_cle in str(val):
            return i
    raise ValueError(f"Mois {mois_cle} non trouvé dans le fichier CSV.")


def extract_month_df(df_raw: pd.DataFrame, year: int, month: int):
    mois_actuel_en = datetime(year, month, 1).strftime("%B").lower()
    mois_cle = MOIS_MAPPING.get(mois_actuel_en)
    if not mois_cle:
        raise ValueError(f"Mapping mois introuvable pour: {mois_actuel_en}")

    mois_col_index = find_month_col_index(df_raw, mois_cle)

    df_mois = df_raw.iloc[1:, mois_col_index:mois_col_index + 3].copy()
    df_mois.columns = ["Jour", "Matin", "Après-midi"]

    # Supprimer les lignes sans jour
    df_mois = df_mois.dropna(subset=["Jour"])
    df_mois = df_mois[df_mois["Jour"].astype(str).str.strip() != ""]

    # Nettoyer les abréviations des jours (ta fonction)
    df_mois["Jour"] = map_jour_with_order(df_mois["Jour"])

    # Ajouter les dates du mois (1..dernier jour)
    last_day = pd.Timestamp(year=year, month=month, day=1).days_in_month
    all_dates = pd.date_range(
        start=f"{year}-{month:02d}-01",
        end=f"{year}-{month:02d}-{last_day}"
    )

    # On coupe à la longueur réelle de df_mois (comme ton code)
    df_mois["Date"] = all_dates[:len(df_mois)].values

    iso = df_mois["Date"].dt.isocalendar()
    df_mois["IsoYear"] = iso.year
    df_mois["Semaine"] = iso.week

    return df_mois


def _month_neighbors(year: int, month: int):
    # retourne (prev_year, prev_month), (next_year, next_month)
    if month == 1:
        prev = (year - 1, 12)
    else:
        prev = (year, month - 1)

    if month == 12:
        nxt = (year + 1, 1)
    else:
        nxt = (year, month + 1)

    return prev, nxt


def get_week_image_for_date(ref_date: date | datetime):
    """
    Retourne un buffer image (BytesIO) pour la semaine contenant ref_date,
    ou None si aucun cours.
    """
    # Normaliser en datetime
    if isinstance(ref_date, datetime):
        ref_dt = ref_date
    else:
        ref_dt = datetime.combine(ref_date, datetime.min.time())

    if ref_dt.weekday() >= 5:  # samedi=5, dimanche=6
        ref_dt += timedelta(days=(7 - ref_dt.weekday()))

    target_iso = ref_dt.isocalendar()
    target_week = target_iso.week
    target_isoyear = target_iso.year

    # Lire le CSV une seule fois
    df_raw = pd.read_csv(SHEET_PATH, header=None, skiprows=3, nrows=32)

    year = ref_dt.year
    month = ref_dt.month
    (py, pm), (ny, nm) = _month_neighbors(year, month)

    # Extraire mois courant + voisins (utile si semaine à cheval)
    parts = []
    for y, m in [(py, pm), (year, month), (ny, nm)]:
        try:
            parts.append(extract_month_df(df_raw, y, m))
        except Exception:
            # si le mois n'existe pas dans le CSV (ou mapping absent), on ignore
            pass

    if not parts:
        raise ValueError("Impossible d'extraire des données de mois depuis le CSV.")

    df_all = pd.concat(parts, ignore_index=True)

    # Filtrer la semaine ISO cible (en tenant compte de l'ISO year)
    df_semaine = df_all[(df_all["Semaine"] == target_week) & (df_all["IsoYear"] == target_isoyear)].copy()
    df_semaine = df_semaine.copy()
    df_semaine[["Matin", "Après-midi"]] = df_semaine[["Matin", "Après-midi"]].fillna("")

    # Si matin = FERIE alors après-midi = FERIE
    mask_ferie = df_semaine["Matin"].astype(str).str.strip().str.upper() == "FERIE"
    df_semaine.loc[mask_ferie, "Après-midi"] = "FERIE"

    # Enlever samedi et dimanche
    df_semaine = df_semaine[~df_semaine["Jour"].isin(["Samedi", "Dimanche"])]

    # Vérifier s'il y a des cours
    if df_semaine.empty or (df_semaine[["Matin", "Après-midi"]].replace("", pd.NA).dropna(how="all").empty):
        return None

    # Remplacer les codes matières par "CODE : Intitulé"
    df_semaine["Matin"] = df_semaine["Matin"].apply(remplacer_code_matiere)
    df_semaine["Après-midi"] = df_semaine["Après-midi"].apply(remplacer_code_matiere)

    df_semaine[["Matin", "Après-midi"]] = (
        df_semaine[["Matin", "Après-midi"]]
        .fillna("Hors jour de cours")
        .replace("", "Hors jour de cours")
        .replace("nan", "Hors jour de cours")
    )

    # Couleurs par cellule
    cell_colors = []
    text_colors = []
    for _, row in df_semaine.iterrows():
        c_matin = couleur_matiere(row["Matin"])
        c_aprem = couleur_matiere(row["Après-midi"])
        cell_colors.append(["#FFFFFF", c_matin, c_aprem])
        text_colors.append(["#000000", couleur_texte(c_matin), couleur_texte(c_aprem)])

    # Créer l'image
    fig_height = max(1.5, 0.6 * len(df_semaine))
    fig, ax = plt.subplots(figsize=(6, fig_height))
    ax.axis("off")

    table = ax.table(
        cellText=df_semaine[["Jour", "Matin", "Après-midi"]].values,
        colLabels=["Jour", "Matin", "Après-midi"],
        cellLoc="center",
        cellColours=cell_colors,
        colWidths=[0.2, 0.4, 0.4],
        loc="center"
    )

    for i, row in enumerate(text_colors):
        for j, color in enumerate(row):
            table[(i + 1, j)].set_text_props(color=color)

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.3)

    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    buf.seek(0)
    plt.close(fig)

    return buf


def get_current_week_image():
    return get_week_image_for_date(date.today())


def map_jour_with_order(jours):
    jours = [str(j).strip().lower() for j in jours]
    result = []
    previous = None

    for jour in jours:
        if jour == "l":
            result.append("Lundi")
        elif jour == "m":
            # If previous was Lundi -> this is Mardi
            # Otherwise -> Mercredi
            if previous == "Lundi":
                result.append("Mardi")
            else:
                result.append("Mercredi")
        elif jour == "me":
            result.append("Mercredi")
        elif jour == "j":
            result.append("Jeudi")
        elif jour == "v":
            result.append("Vendredi")
        elif jour == "s":
            result.append("Samedi")
        elif jour == "d":
            result.append("Dimanche")
        else:
            result.append(jour)  # unknown, leave as is
        previous = result[-1]
    return result


# ===========================
# COMMANDE DISCORD : /planning
# ===========================
@bot.tree.command(name="planning", description="Afficher le planning de la semaine (option: date)")
@app_commands.describe(date="Date de référence au format DD-MM-YYY (ex: 02-03-2026)")
async def planning(interaction: discord.Interaction, date: str | None = None):
    await interaction.response.defer()

    try:
        # ✅ Si aucune date n’est fournie -> comportement actuel
        if not date:
            image_buf = get_current_week_image()
        else:
            # ✅ Sinon -> semaine contenant la date fournie
            try:
                ref_date = parse_iso_date(date)
            except ValueError:
                await interaction.followup.send("❌ Format invalide. Utilise `YYYY-MM-DD` (ex: `2026-03-02`).")
                return

            image_buf = get_week_image_for_date(ref_date)

        if image_buf is None:
            msg = "ℹ️ Aucun cours cette semaine."
            if date:
                msg = f"ℹ️ Aucun cours la semaine contenant le `{date}`."
            await interaction.followup.send(msg)
            return

        await interaction.followup.send(file=discord.File(fp=image_buf, filename="planning.png"))

    except Exception as e:
        tb_list = traceback.extract_tb(e.__traceback__)
        if tb_list:
            last = tb_list[-1]
            line_info = f"{os.path.basename(last.filename)}:{last.lineno}"
        else:
            line_info = "ligne inconnue"

        await interaction.followup.send(
            f"❌ Erreur lors de la récupération du planning : {type(e).__name__}: {e}\n{line_info}"
        )


# ===========================
# DÉMARRAGE DU BOT
# ===========================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synchronisées")
    except Exception as e:
        print(f"❌ Erreur de sync : {e}")

bot.run(TOKEN)
