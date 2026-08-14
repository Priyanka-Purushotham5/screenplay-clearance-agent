import scriptMeta from "@/lib/fixtures/script-meta.json";

export async function GET() {
  return Response.json(scriptMeta);
}
