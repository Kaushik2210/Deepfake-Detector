/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@veriframe/core"],
  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
