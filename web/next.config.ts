import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // 关掉左下角 Next Dev Tools 浮层（Theme/Position/Hide 那些），不是产品设置
  devIndicators: false,
  async redirects() {
    return [{ source: "/research", destination: "/strategies", permanent: true }];
  },
};

export default nextConfig;
