/**
 * JavaScript API Client Tests
 * Tests BigInt handling and API client functionality
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock fetch globally
global.fetch = vi.fn();

describe('ApiClient BigInt Handling', () => {
    let ApiClient;

    beforeEach(async () => {
        vi.resetAllMocks();
        // Import the module fresh for each test
        const module = await import('../assets/static/js/modules/api.js');
        ApiClient = module.ApiClient;
    });

    it('should parse string IDs to BigInt', () => {
        const client = new ApiClient();

        const input = {
            guild_id: '123456789012345678',
            channel: '987654321098765432',
            role_id: '111111111111111111',
            user_id: '222222222222222222',
            users: [
                { id: '333333333333333333', name: 'user1' }
            ],
            name: 'test guild',
            count: 42,
        };

        const result = client.parseBigInts(input);

        expect(typeof result.guild_id).toBe('bigint');
        expect(result.guild_id).toBe(BigInt('123456789012345678'));

        expect(typeof result.channel).toBe('bigint');
        expect(result.channel).toBe(BigInt('987654321098765432'));

        expect(typeof result.role_id).toBe('bigint');
        expect(result.role_id).toBe(BigInt('111111111111111111'));

        expect(typeof result.user_id).toBe('bigint');
        expect(result.user_id).toBe(BigInt('222222222222222222'));

        expect(typeof result.users[0].id).toBe('bigint');

        // Non-ID fields should remain unchanged
        expect(result.name).toBe('test guild');
        expect(result.count).toBe(42);
    });

    it('should stringify BigInt values for JSON', () => {
        const client = new ApiClient();

        const input = {
            guild_id: BigInt('123456789012345678'),
            channel: BigInt('987654321098765432'),
            name: 'test',
            count: 42,
        };

        const result = client.stringifyBigInts(input);

        expect(result.guild_id).toBe('123456789012345678');
        expect(result.channel).toBe('987654321098765432');
        expect(result.name).toBe('test');
        expect(result.count).toBe(42);
    });

    it('should handle nested arrays with BigInts', () => {
        const client = new ApiClient();

        const input = {
            channels: [
                { id: '111111111111111111', name: 'channel1' },
                { id: '222222222222222222', name: 'channel2' },
            ],
        };

        const result = client.parseBigInts(input);

        expect(Array.isArray(result.channels)).toBe(true);
        expect(typeof result.channels[0].id).toBe('bigint');
        expect(result.channels[0].id).toBe(BigInt('111111111111111111'));
    });

    it('should handle null and undefined values', () => {
        const client = new ApiClient();

        const input = {
            nullValue: null,
            undefinedValue: undefined,
            nested: {
                nullValue: null,
                undefinedValue: undefined,
            },
        };

        const result = client.parseBigInts(input);

        expect(result.nullValue).toBeNull();
        expect(result.undefinedValue).toBeUndefined();
        expect(result.nested.nullValue).toBeNull();
    });

    it('should not convert non-numeric strings', () => {
        const client = new ApiClient();

        const input = {
            name: 'test guild',
            slug: 'test-guild',
            webhook_url: 'https://discord.com/api/webhooks/123/abc',
            empty: '',
        };

        const result = client.parseBigInts(input);

        expect(result.name).toBe('test guild');
        expect(result.slug).toBe('test-guild');
        expect(result.webhook_url).toBe('https://discord.com/api/webhooks/123/abc');
        expect(result.empty).toBe('');
    });
});

describe('ApiClient fetch', () => {
    let ApiClient;

    beforeEach(async () => {
        vi.resetAllMocks();
        const module = await import('../assets/static/js/modules/api.js');
        ApiClient = module.ApiClient;
    });

    it('should handle successful response', async () => {
        const client = new ApiClient();

        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ success: true, data: 'test' }),
        });

        const result = await client.fetch('/api/test');

        expect(result).toEqual({ success: true, data: 'test' });
    });

    it('should handle error response', async () => {
        const client = new ApiClient();

        global.fetch.mockResolvedValueOnce({
            ok: false,
            status: 404,
            json: async () => ({ error: 'Not found' }),
        });

        await expect(client.fetch('/api/test')).rejects.toThrow('Not found');
    });

    it('should include BigInt values in request body via data parameter', async () => {
        const client = new ApiClient();

        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ success: true }),
        });

        // Test using the data parameter which gets stringified internally
        await client.saveGuild(1234567890, {
            guild_id: BigInt('123456789012345678'),
            name: 'test',
        });

        expect(global.fetch).toHaveBeenCalledWith(
            '/api/guilds/1234567890',
            expect.objectContaining({
                method: 'POST',
                body: expect.any(String),
            })
        );

        // Verify the body was properly stringified with BigInt converted to string
        const callArgs = global.fetch.mock.calls[0];
        const body = JSON.parse(callArgs[1].body);
        expect(body.guild_id).toBe('123456789012345678');
        expect(body.name).toBe('test');
    });
});
