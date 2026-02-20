import js from '@eslint/js';
import globals from 'globals';

export default [
    // Recommended base configuration
    js.configs.recommended,

    {
        // Files to lint
        files: ['assets/static/js/**/*.js', 'attubot/web/static/js/**/*.js'],

        languageOptions: {
            ecmaVersion: 2024,
            sourceType: 'script', // Using traditional script mode (not modules)
            globals: {
                ...globals.browser,
                // UIkit is loaded globally via CDN
                UIkit: 'readonly',
                // Bootstrap is loaded globally via CDN
                bootstrap: 'readonly',
                // Feather icons are loaded globally via CDN
                feather: 'readonly',
            },
        },

        rules: {
            // Modern best practices
            'no-unused-vars': ['warn', {
                argsIgnorePattern: '^_',
                varsIgnorePattern: '^_'
            }],
            'no-console': ['warn', { allow: ['warn', 'error'] }],
            'prefer-const': 'warn',
            'no-var': 'error',
            'eqeqeq': ['error', 'always', { null: 'ignore' }],
            'curly': ['error', 'all'],

            // Code quality
            'no-unused-expressions': 'error',
            'no-duplicate-imports': 'error',
            'no-template-curly-in-string': 'warn',
            'require-await': 'warn',

            // Style consistency
            'semi': ['error', 'always'],
            'quotes': ['warn', 'single', { avoidEscape: true }],
            'indent': ['warn', 4, { SwitchCase: 1 }],
            'comma-dangle': ['warn', 'only-multiline'],
            'space-before-function-paren': ['warn', {
                anonymous: 'never',
                named: 'never',
                asyncArrow: 'always'
            }],

            // Modern JavaScript features
            'prefer-arrow-callback': 'warn',
            'prefer-template': 'warn',
            'object-shorthand': ['warn', 'always'],
            'prefer-destructuring': ['warn', {
                array: false,
                object: true
            }, {
                enforceForRenamedProperties: false
            }],

            // Async/await best practices
            'no-async-promise-executor': 'error',
            'no-await-in-loop': 'warn',
            'no-return-await': 'error',
        },
    },

    {
        // ES module JS files (modules, pages, components, and main entry points)
        files: [
            'assets/static/js/modules/**/*.js',
            'assets/static/js/pages/**/*.js',
            'assets/static/js/components/**/*.js',
            'assets/static/js/main.js',
            'attubot/web/static/js/modules/**/*.js',
            'attubot/web/static/js/pages/**/*.js',
            'attubot/web/static/js/components/**/*.js',
            'attubot/web/static/js/main.js',
        ],

        languageOptions: {
            ecmaVersion: 2024,
            sourceType: 'module',
            globals: {
                ...globals.browser,
                bootstrap: 'readonly',
                feather: 'readonly',
            },
        },
    },

    {
        // Test files (vitest + jsdom)
        files: ['tests/**/*.test.js'],

        languageOptions: {
            ecmaVersion: 2024,
            sourceType: 'module',
            globals: {
                ...globals.browser,
                ...globals.node,
                // Vitest globals (enabled via globals: true in vitest.config.js)
                vi: 'readonly',
                describe: 'readonly',
                it: 'readonly',
                expect: 'readonly',
                beforeEach: 'readonly',
                afterEach: 'readonly',
                beforeAll: 'readonly',
                afterAll: 'readonly',
            },
        },

        rules: {
            'no-console': 'off',
        },
    },

    {
        // Ignore patterns
        ignores: [
            'node_modules/**',
            '.git/**',
            '.pytest_cache/**',
            '.ruff_cache/**',
            '__pycache__/**',
            '*.min.js',
            'dist/**',
            'build/**',
        ],
    },
];
