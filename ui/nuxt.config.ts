// https://nuxt.com/docs/api/configuration/nuxt-config

// Cron expression for the in-process pipeline schedule; default 07:00 daily, "" disables it.
const pipelineSchedule = process.env.NUXT_PIPELINE_SCHEDULE ?? '0 7 * * *'

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
    pipelineCommand: 'uv run jobs run',
    public: {
      // Informational only; the actual cron is fixed at startup (see nitro.scheduledTasks).
      pipelineSchedule
    }
  },

  compatibilityDate: '2026-06-30',

  nitro: {
    // Native module: keep it external instead of bundling it into the server build.
    externals: { external: ['better-sqlite3'] },
    // Scheduled tasks are resolved at build/startup, so the schedule is read from the
    // environment here rather than from runtimeConfig. Set NUXT_PIPELINE_SCHEDULE="" to disable.
    experimental: { tasks: true },
    scheduledTasks: pipelineSchedule ? { [pipelineSchedule]: ['pipeline'] } : {}
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
