import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    ignores: ['dist/**', 'public/**', 'node_modules/**', '.venv/**', 'types/**', '**/*.d.ts'],
  },

  // Desk frontend: TypeScript + Vue SFCs. Correctness rules only - formatting
  // is left to the editor; vue-tsc does the type checking.
  {
    files: ['frontend/src/**/*.{ts,vue}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended, ...pluginVue.configs['flat/essential']],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { parser: tseslint.parser, extraFileExtensions: ['.vue'] },
    },
    rules: {
      // Undefined names are vue-tsc's job (it knows auto-imports and globals).
      'no-undef': 'off',
      // Expressions compiled from DocType metadata (depends_on, eval: filters)
      // are the only sanctioned `new Function` uses - each one is marked.
      'no-new-func': 'error',
      'no-empty': ['error', { allowEmptyCatch: true }],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-expressions': ['error', { allowShortCircuit: true, allowTernary: true }],
      '@typescript-eslint/no-empty-object-type': ['error', { allowInterfaces: 'with-single-extends' }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
      ],
      // shadcn-vue components (ui/) are single-word by design.
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    // Ad-hoc components in tests use the plain props shorthand.
    files: ['frontend/src/**/__tests__/**', 'frontend/src/**/*.spec.ts'],
    rules: { 'vue/require-prop-type-constructor': 'off' },
  },

  // DocType client scripts: plain scripts run by core/scripting/executor.ts
  // inside `new Function(...)` - its parameters are the globals, and the
  // top-level handlers are called by name, not referenced.
  {
    files: ['grunt/**/doctypes/**/*.js'],
    extends: [js.configs.recommended],
    languageOptions: {
      sourceType: 'script',
      globals: {
        ...globals.browser,
        cur_frm: 'readonly',
        frm: 'readonly',
        grunt: 'readonly',
        __: 'readonly',
        listview: 'readonly',
        change: 'readonly',
      },
    },
    rules: {
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-unused-vars': [
        'error',
        {
          args: 'none',
          caughtErrors: 'none',
          varsIgnorePattern:
            '^(on_load|on_change|validate|before_save|after_save|on_transitions|setup_list|on_quick_filter_change|_.*)$',
        },
      ],
    },
  },
)
