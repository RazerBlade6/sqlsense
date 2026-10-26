/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export, served from S3 behind CloudFront.
  output: "export",
};

export default nextConfig;
