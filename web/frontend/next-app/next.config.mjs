/** @type {import('next').NextConfig} */
const nextConfig = {
  // 单端口形态：构建产物为纯静态站点（out/），由后端 Flask 托管；
  // dev 模式不受影响（output 仅作用于 next build）
  output: "export",
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
  turbopack: {},
}

export default nextConfig
