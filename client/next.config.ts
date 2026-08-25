import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Emits .next/standalone — a self-contained server for slim Docker images.
  output: 'standalone',
}

export default nextConfig
