# SPDX-License-Identifier: Apache-2.0
"""nova_core.eggs.data | egg game constants: rarities, pools, durations, drop weights."""

rarities: list[str] = ['common', 'uncommon', 'rare', 'legendary', 'mythical']

# seconds until each rarity hatches
hatch_durations: dict[str, int] = {
    'common': 30 * 60,  # 30 min
    'uncommon': 2 * 3600,  # 2 hours
    'rare': 8 * 3600,  # 8 hours
    'legendary': 24 * 3600,  # 24 hours
    'mythical': 48 * 3600,  # 48 hours
}

# drop weights; index-aligned with rarities
drop_weights: list[int] = [55, 25, 13, 5, 2]

hatch_pools: dict[str, list[str]] = {
    'common': [
        '🐣',
        '🐤',
        '🐥',
        '🐔',
        '🐧',
        '🦆',
        '🐦',
        '🐦‍⬛',
        '🐸',
        '🐍',
        '🐛',
        '🐝',
        '🐜',
        '🐞',
        '🪱',
        '🐌',
        '🪳',
        '🐟',
        '🐶',
        '🐱',
        '🐭',
        '🐹',
        '🐰',
        '🐷',
        '🐮',
        '🐵',
        '🍬',
    ],
    'uncommon': [
        '🦉',
        '🕊️',
        '🦃',
        '🐓',
        '🪿',
        '🐢',
        '🦎',
        '🦋',
        '🦗',
        '🪲',
        '🦟',
        '🐠',
        '🦐',
        '🦀',
        '🐡',
        '🦪',
        '🦊',
        '🐻',
        '🐼',
        '🐨',
        '🦝',
        '🐺',
        '🍭',
    ],
    'rare': [
        '🦩',
        '🦢',
        '🦜',
        '🦚',
        '🐊',
        '🐲',
        '🐙',
        '🦑',
        '🦞',
        '🦈',
        '🐬',
        '🐋',
        '🕷️',
        '🦂',
        '🦁',
        '🐯',
        '🐘',
        '🦒',
        '🦓',
        '🍫',
    ],
    'legendary': ['🦅', '🦤', '🦖', '🦕', '🪼', '🦏', '🦛', '🦘', '🦬', '🐻‍❄️', '🦙', '🦭'],
    'mythical': ['🐉', '🦄', '🐦‍🔥'],
}
