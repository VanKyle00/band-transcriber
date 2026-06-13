/** @type {import('next').NextConfig} */
const nextConfig = {
  // Uploaded audio can be large; allow generous request bodies on the submit route.
  experimental: {
    serverActions: { bodySizeLimit: "100mb" },
  },
};

export default nextConfig;
