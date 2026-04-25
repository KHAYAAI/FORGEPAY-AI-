import { loadEnv, defineConfig } from "@medusajs/framework/utils"

loadEnv(process.env.NODE_ENV ?? "development", process.cwd())

module.exports = defineConfig({
  projectConfig: {
    databaseUrl: process.env.DATABASE_URL,
    redisUrl: process.env.REDIS_URL,
    http: {
      storeCors: process.env.STORE_CORS ?? "http://localhost:8080",
      adminCors: process.env.MEDUSA_ADMIN_CORS ?? "http://localhost:7001",
      authCors: process.env.MEDUSA_ADMIN_CORS ?? "http://localhost:7001",
      jwtSecret: process.env.JWT_SECRET ?? "supersecret",
      cookieSecret: process.env.COOKIE_SECRET ?? "supersecret",
    },
  },
  modules: [
    {
      resolve: "./src/modules/rfq",
    },
  ],
})
