import runFindings from "@/lib/fixtures/run-findings.json";

export async function GET() {
  return Response.json(runFindings);
}
