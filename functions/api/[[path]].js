export async function onRequest(context) {
  const url = new URL(context.request.url);

  // Optional: Remove /api if your worker expects routes to start at root /
  // url.pathname = url.pathname.replace(/^\/api/, '');

  return await context.env.API.fetch(new Request(url, context.request));
}