/**
 * Config Models Tests
 * Tests GuildConfig, ThemeConfig, and SystemConfig
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

// mock api module so config.js can be imported without a real server
vi.mock('/apps/bot/legacy_web/static/js/modules/api.js', () => ({
    api: {
        getGuild: vi.fn(),
        saveGuild: vi.fn(),
        getTheme: vi.fn(),
        saveTheme: vi.fn(),
        getSystem: vi.fn(),
        saveSystem: vi.fn(),
        getChat: vi.fn(),
        saveChat: vi.fn(),
    },
}));

describe('GuildConfig', () => {
    let GuildConfig;

    beforeEach(async () => {
        vi.resetAllMocks();
        const module = await import('/apps/bot/legacy_web/static/js/modules/config.js');
        GuildConfig = module.GuildConfig;
    });

    it('should initialize with defaults when no data given', () => {
        const cfg = new GuildConfig();

        expect(cfg.id).toBe(BigInt(0));
        expect(cfg.name).toBe('');
        expect(cfg.channels).toEqual({});
        expect(cfg.epoch).toEqual({});
        expect(cfg.roles).toEqual({});
        expect(cfg.users).toEqual({});
        expect(cfg.starboard).toEqual({});
    });

    it('should parse guild_id as BigInt', () => {
        const cfg = new GuildConfig({ guild_id: BigInt('123456789012345678') });
        expect(cfg.id).toBe(BigInt('123456789012345678'));
    });

    it('should parse id field as BigInt', () => {
        const cfg = new GuildConfig({ id: BigInt('987654321098765432') });
        expect(cfg.id).toBe(BigInt('987654321098765432'));
    });

    it('should store channels from data', () => {
        const cfg = new GuildConfig({
            channels: { activity: BigInt('111111111111111111'), logs: BigInt('222222222222222222') },
        });
        expect(cfg.channels.activity).toBe(BigInt('111111111111111111'));
        expect(cfg.channels.logs).toBe(BigInt('222222222222222222'));
    });

    it('should store starboard from data', () => {
        const cfg = new GuildConfig({
            starboard: {
                channel_id: BigInt('555555555555555555'),
                emojis: { '⭐': '#eedd20', '<:custom:123456789012345678>': '#aabbcc' },
                valid_bots: [BigInt('111111111111111111')],
            },
        });

        expect(cfg.starboard.channel_id).toBe(BigInt('555555555555555555'));
        expect(cfg.starboard.emojis['⭐']).toBe('#eedd20');
        expect(cfg.starboard.emojis['<:custom:123456789012345678>']).toBe('#aabbcc');
        expect(cfg.starboard.valid_bots[0]).toBe(BigInt('111111111111111111'));
    });

    it('toJSON should include starboard', () => {
        const cfg = new GuildConfig({
            channels: { activity: BigInt('111111111111111111') },
            starboard: {
                channel_id: BigInt('555555555555555555'),
                emojis: { '⭐': '#eedd20' },
                valid_bots: [],
            },
        });

        const json = cfg.toJSON();

        expect(json).toHaveProperty('starboard');
        expect(json.starboard.channel_id).toBe(BigInt('555555555555555555'));
        expect(json.starboard.emojis['⭐']).toBe('#eedd20');
    });

    it('toJSON should not include id or name', () => {
        const cfg = new GuildConfig({ id: BigInt('123'), name: 'test' });
        const json = cfg.toJSON();

        expect(json).not.toHaveProperty('id');
        expect(json).not.toHaveProperty('guild_id');
        expect(json).not.toHaveProperty('name');
    });

    it('getChannel should return BigInt 0 for missing channel', () => {
        const cfg = new GuildConfig();
        expect(cfg.getChannel('activity')).toBe(BigInt(0));
    });

    it('getChannel should return channel ID as BigInt', () => {
        const cfg = new GuildConfig({
            channels: { activity: BigInt('111111111111111111') },
        });
        expect(cfg.getChannel('activity')).toBe(BigInt('111111111111111111'));
    });

    it('getEpochYear should return 1 by default', () => {
        expect(new GuildConfig().getEpochYear()).toBe(1);
    });

    it('getYearLength should return 365 by default', () => {
        expect(new GuildConfig().getYearLength()).toBe(365);
    });

    it('isPaused should return false by default', () => {
        expect(new GuildConfig().isPaused()).toBe(false);
    });

    it('isPaused should reflect epoch.paused', () => {
        const cfg = new GuildConfig({ epoch: { paused: true } });
        expect(cfg.isPaused()).toBe(true);
    });
});

describe('ThemeConfig', () => {
    let ThemeConfig;

    beforeEach(async () => {
        vi.resetAllMocks();
        const module = await import('/apps/bot/legacy_web/static/js/modules/config.js');
        ThemeConfig = module.ThemeConfig;
    });

    it('should initialize with defaults', () => {
        const cfg = new ThemeConfig();
        expect(cfg.rotation).toBe(0.0);
        expect(cfg.max_rate).toBe(0.5);
        expect(cfg.bot_color).toBe('#ff0000');
        expect(cfg.guild_color).toBe('#ffffff');
    });

    it('toJSON should include all fields', () => {
        const cfg = new ThemeConfig({ rotation: 0.25, max_rate: 1.0, bot_color: '#abcdef', guild_color: '#123456' });
        const json = cfg.toJSON();
        expect(json.rotation).toBe(0.25);
        expect(json.max_rate).toBe(1.0);
        expect(json.bot_color).toBe('#abcdef');
        expect(json.guild_color).toBe('#123456');
    });

    it('getRotationDegrees should multiply by 360', () => {
        const cfg = new ThemeConfig({ rotation: 0.5 });
        expect(cfg.getRotationDegrees()).toBe(180);
    });
});

describe('SystemConfig', () => {
    let SystemConfig;

    beforeEach(async () => {
        vi.resetAllMocks();
        const module = await import('/apps/bot/legacy_web/static/js/modules/config.js');
        SystemConfig = module.SystemConfig;
    });

    it('should initialize with defaults', () => {
        const cfg = new SystemConfig();
        expect(cfg.version).toBe('');
        expect(cfg.primary_guild).toBe(BigInt(0));
        expect(cfg.error_log_guild).toBe(BigInt(0));
        expect(cfg.error_log_channel).toBe(BigInt(0));
        expect(cfg.error_hook).toBe('');
    });

    it('should parse BigInt fields', () => {
        const cfg = new SystemConfig({
            primary_guild: BigInt('111111111111111111'),
            error_log_guild: BigInt('222222222222222222'),
            error_log_channel: BigInt('333333333333333333'),
        });
        expect(cfg.primary_guild).toBe(BigInt('111111111111111111'));
        expect(cfg.error_log_guild).toBe(BigInt('222222222222222222'));
        expect(cfg.error_log_channel).toBe(BigInt('333333333333333333'));
    });

    it('isErrorLoggingConfigured should be false when not set', () => {
        expect(new SystemConfig().isErrorLoggingConfigured()).toBe(false);
    });

    it('isErrorLoggingConfigured should be true when both guild and channel are set', () => {
        const cfg = new SystemConfig({
            error_log_guild: BigInt('222222222222222222'),
            error_log_channel: BigInt('333333333333333333'),
        });
        expect(cfg.isErrorLoggingConfigured()).toBe(true);
    });
});

