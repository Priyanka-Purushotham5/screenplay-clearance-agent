import scriptScenes from "@/lib/fixtures/script-scenes.json";

export async function GET() {
  return Response.json(scriptScenes);
}
