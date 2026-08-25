"""Generic embed paginator used by collection/shop/market/leaderboard commands."""
from __future__ import annotations

from typing import Callable

import discord


class Paginator(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        pages: list[discord.Embed],
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.pages = pages or [discord.Embed(description="Rien à afficher.")]
        self.index = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.first.disabled = self.index == 0
        self.prev.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1
        self.last.disabled = self.index >= len(self.pages) - 1
        if len(self.pages) > 1:
            self.pages[self.index].set_footer(text=f"Page {self.index + 1}/{len(self.pages)}")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seule la personne ayant lancé la commande peut naviguer ici.", ephemeral=True
            )
            return False
        return True

    async def _update(self, interaction: discord.Interaction) -> None:
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="⏮", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.index = 0
        await self._update(interaction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.index = max(0, self.index - 1)
        await self._update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        await self._update(interaction)

    @discord.ui.button(label="⏭", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.index = len(self.pages) - 1
        await self._update(interaction)


def chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]
