from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.pagination import Paginator

CATEGORIES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("👤 Profil & Économie", "Ton compte, ton argent, ta progression.", [
        ("/start", "Crée ton profil et ton équipe de départ."),
        ("/profile [membre]", "Affiche un profil : KP, rang, cartes, bilan."),
        ("/daily", f"Récupère {config.DAILY_REWARD} {config.CURRENCY_SYMBOL} toutes les 24h."),
    ]),
    ("🃏 Claim & Collection", "Recrute des joueurs et gère ta collection.", [
        ("/claim", "Réclame un joueur Inazuma aléatoire (toutes les 30 min), puis garde-le ou vends-le."),
        ("/collection [membre] [poste] [rareté]", "Liste tes joueurs possédés, avec filtres."),
        ("/card <id>", "Affiche la carte détaillée d'un joueur."),
        ("/sell <id>", "Vend une carte contre des KP."),
        ("/lock <id> / /unlock <id>", "Verrouille/déverrouille une carte contre la vente ou l'échange accidentel."),
    ]),
    ("👕 Équipe", "Compose ta formation, ton onze de départ et ton banc.", [
        ("/team view [membre]", "Affiche la composition actuelle et la puissance d'équipe."),
        ("/team formation <formation>", "Change de formation (4-4-2, 4-3-3, 3-5-2, 5-3-2, 4-5-1, 4-2-3-1, 3-4-3)."),
        ("/team set <slot> <id>", "Place une carte dans un slot (titulaire, doit correspondre au poste)."),
        ("/team bench <id>", "Envoie une carte sur le banc."),
        ("/team remove <slot>", "Vide un slot."),
        ("/team equip <id> <technique>", "Équipe une technique achetée sur un joueur."),
        ("/team unequip <id>", "Retire la technique équipée."),
        ("/team tactic <id>", "Équipe une tactique d'équipe possédée."),
        ("/team coach <id>", "Équipe un coach possédé."),
        ("/team rename <nom>", "Renomme ton équipe."),
    ]),
    ("🏪 Boutique", "Achète techniques, tactiques et coachs avec tes KP.", [
        ("/shop techniques", "Liste les techniques (hissatsu) à l'achat."),
        ("/shop tactics", "Liste les tactiques d'équipe à l'achat."),
        ("/shop coaches", "Liste les coachs à l'achat."),
        ("/technique <id>", "Affiche la carte détaillée (avec image générée) d'une technique."),
        ("/coach <id>", "Affiche la carte détaillée (avec image générée) d'un coach."),
        ("/buy technique <id>", "Achète une technique."),
        ("/buy tactic <id>", "Achète une tactique."),
        ("/buy coach <id>", "Achète un coach."),
        ("/inventory", "Liste tes techniques/tactiques/coachs possédés avec leurs IDs."),
    ]),
    ("🏦 Marché des Transferts", "Achète et vends des joueurs entre membres du serveur.", [
        ("/market list <id> <prix>", "Met une de tes cartes en vente."),
        ("/market browse [poste] [prix max]", "Parcourt les annonces actives."),
        ("/market buy <annonce>", "Achète une carte listée."),
        ("/market cancel <annonce>", "Annule une de tes annonces."),
        ("/market mine", "Affiche tes annonces actives."),
    ]),
    ("🔄 Échanges", "Négocie un échange direct de cartes/KP avec un autre membre.", [
        ("/trade propose <membre> ...", "Propose un échange (cartes + KP dans les deux sens)."),
        ("/trade cancel <échange>", "Annule un échange que tu as proposé."),
    ]),
    ("⚔️ Combat & Ranked", "Affronte les équipes des autres membres et grimpe le classement.", [
        ("/battle challenge <membre>", "Défie un membre en 1v1 équipe contre équipe (11 titulaires requis)."),
        ("/battle history", "Affiche tes 5 derniers combats."),
    ]),
    ("📊 Classements", "Compare-toi au reste du serveur.", [
        ("/leaderboard rank", "Classement par points de rang (ranked)."),
        ("/leaderboard rich", f"Classement par {config.CURRENCY_NAME}."),
        ("/leaderboard wins", "Classement par victoires en combat."),
    ]),
]


class HelpCog(commands.Cog):
    """Liste toutes les commandes du bot, façon soccerguru.live/commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Affiche toutes les commandes d'INAZUMA BOT par catégorie.")
    async def help_cmd(self, interaction: discord.Interaction):
        pages = []
        for title, subtitle, commands_list in CATEGORIES:
            lines = [f"**`{name}`**\n{desc}" for name, desc in commands_list]
            embed = discord.Embed(
                title=f"⚽ INAZUMA BOT — {title}",
                description=f"_{subtitle}_\n\n" + "\n\n".join(lines),
                color=config.rarity_embed_color(4),
            )
            pages.append(embed)
        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
