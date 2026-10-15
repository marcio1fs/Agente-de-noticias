/** Backend is resolved server-side, so browser calls stay on the same origin. */
const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
