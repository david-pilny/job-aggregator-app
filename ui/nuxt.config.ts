// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@vueuse/nuxt'
  ],

  devtools: {
    enabled: true
  },

  css: ['~/assets/css/main.css'],

  // Overridable with NUXT_DB_PATH, NUXT_PIPELINE_CWD, NUXT_PIPELINE_COMMAND in .env.
  runtimeConfig: {
    dbPath: '../jobs.sqlite',
    pipelineCwd: '..',
    pipelineCommand: 'uv run jobs run'
  },

  compatibilityDate: '2026-06-30',

  nitro: {
    // Native module: keep it external instead of bundling it into the server build.
    externals: { external: ['better-sqlite3'] }
  },

  typescript: {
    strict: true,
    typeCheck: false
  },

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  }
})
