/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@veriframe/core"],

  // These are server-only and load native/optional dependencies at runtime.
  // Bundling them makes webpack try to resolve BullMQ's optional Valkey client,
  // which isn't installed and isn't needed for the Redis connection we use.
  serverExternalPackages: ["bullmq", "ioredis", "postgres"],

  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
