import discord
from discord.ext import commands
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from dotenv import load_dotenv
import calendar
import io
import os

load_dotenv()

# ===========================
# CONFIGURATION
# ===========================
TOKEN = str(os.getenv("DISCORD_TOKEN"))
SHEET_PATH = str(os.getenv("EDT_PATH"))

# ===========================
# BOT SETUP
# ===========================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# Dictionnaire de correspondance codes -> intitulés
matiere_map = {
    "UTC501": "Maths",
    "UTC502": "OS",
    "UTC503": "Programmation",
    "UTC504": "SI et BD",
    "UTC505": "Réseaux",
    "GDN100": "Gestion"
}

def remplacer_code_matiere(code):
    code = str(code).strip()
    if code in matiere_map:
        return f"{code} : {matiere_map[code]}"
    return code

matiere_colors = {
    "UTC501": "#FFD700",
    "UTC502": "#87CEFA",
    "UTC503": "#90EE90",
    "UTC504": "#FFB6C1",
    "UTC505": "#FFA07A",
    "GDN100": "#D3D3D3"
}

def couleur_matiere(code):
    if code is None:
        return "#FFFFFF"
    code = str(code).split(" :")[0].strip()
    return matiere_colors.get(code, "#FFFFFF")


# ===========================
# JOUR ABBR → JOUR COMPLET (avec ordre)
# ===========================
def map_jour_with_order(jours):
    jours = [str(j).strip().lower() for j in jours]
    result = []
    previous = None

    for jour in jours:
        if jour == "l":
            result.append("Lundi")
        elif jour == "m":
            # If previous was Lundi -> Mardi, else Mercredi
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
            result.append(jour)
        previous = result[-1]

    return result


# ===========================
# FONCTION : Récupération du planning
# ===========================
def get_current_week_image():

    # Lire le CSV
    df = pd.read_csv(SHEET_PATH, header=None, skiprows=3, nrows=32)

    # Trouver le mois actuel
    mois_actuel_en = datetime.now().strftime("%B").lower()
    mois_mapping = {
        "january": "JANVIER", "february": "FEVRIER", "march": "MARS",
        "april": "AVRIL", "may": "MAI", "june": "JUIN",
        "july": "JUILLET", "august": "AOUT", "september": "SEPTEMBRE",
        "october": "OCTOBRE", "november": "NOVEMBRE", "december": "DECEMBRE"
    }
    mois_cle = mois_mapping.get(mois_actuel_en)

    # Trouver la colonne du mois
    header_row = df.iloc[0].astype(str)
    mois_col_index = None
    for i, val in enumerate(header_row):
        if mois_cle in val:
            mois_col_index = i
            break
    if mois_col_index is None:
        raise ValueError(f"Mois {mois_cle} non trouvé dans le fichier CSV.")

    # Extraire colonnes du mois
    df_mois = df.iloc[1:, mois_col_index:mois_col_index + 3]
    df_mois.columns = ["Jour", "Matin", "Après-midi"]

    # Nettoyer
    df_mois = df_mois.dropna(subset=["Jour"])
    df_mois = df_mois[df_mois["Jour"].astype(str).str.strip() != ""]

    # Transformer les abréviations
    df_mois["Jour"] = map_jour_with_order(df_mois["Jour"])

    # === 🟦 Génération des dates sans jour fantôme ===
    annee = datetime.now().year
    mois_num = datetime.now().month
    nb_jours = calendar.monthrange(annee, mois_num)[1]

    dates = []
    current_day = 1

    for _ in df_mois["Jour"]:
        if current_day <= nb_jours:
            dates.append(datetime(annee, mois_num, current_day))
        else:
            dates.append(pd.NaT)  # sécurité
        current_day += 1

    df_mois["Date"] = dates
    df_mois["Semaine"] = df_mois["Date"].dt.isocalendar().week

    # Semaine actuelle (samedi/dimanche -> semaine suivante)
    aujourdhui = datetime.now()
    if aujourdhui.weekday() >= 5:
        aujourdhui += timedelta(days=(7 - aujourdhui.weekday()))
    semaine_courante = aujourdhui.isocalendar()[1]

    df_semaine = df_mois[df_mois["Semaine"] == semaine_courante]
    df_semaine = df_semaine[~df_semaine["Jour"].isin(["Samedi", "Dimanche"])]

    if df_semaine.empty or (df_semaine[['Matin','Après-midi']].replace('', pd.NA).dropna(how='all').empty):
        return None

    # Remplacer les codes matières
    df_semaine['Matin'] = df_semaine['Matin'].apply(remplacer_code_matiere)
    df_semaine['Après-midi'] = df_semaine['Après-midi'].apply(remplacer_code_matiere)

    # Couleurs
    cell_colors = []
    for _, row in df_semaine.iterrows():
        cell_colors.append([
            "#FFFFFF",
            couleur_matiere(row['Matin']),
            couleur_matiere(row['Après-midi'])
        ])

    # Générer l’image
    fig_height = max(1.5, 0.6 * len(df_semaine))
    fig, ax = plt.subplots(figsize=(6, fig_height))
    ax.axis("off")

    table = ax.table(
        cellText=df_semaine[['Jour','Matin','Après-midi']].values,
        colLabels=['Jour','Matin','Après-midi'],
        cellLoc='center',
        cellColours=cell_colors,
        colWidths=[0.2, 0.4, 0.4],
        loc='center'
    )

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.3)

    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    plt.close(fig)

    return buf


# ===========================
# COMMANDE DISCORD : /planning
# ===========================
@bot.tree.command(name="planning", description="Afficher le planning de la semaine")
async def planning(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        image_buf = get_current_week_image()
        if image_buf is None:
            await interaction.followup.send("📭 Aucun cours cette semaine.")
        else:
            await interaction.followup.send(file=discord.File(fp=image_buf, filename="planning.png"))
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur lors de la récupération du planning : {e}")


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
