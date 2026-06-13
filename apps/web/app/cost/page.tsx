export const metadata = { title: "Hosting cost — Band Transcriber" };

export default function CostPage() {
  return (
    <>
      <h1>Hosting cost</h1>
      <p className="lede">
        Serverless GPU, scale-to-zero — you pay only for seconds used. Figures verified
        mid-2026. Per-song = one ~3.5-min track through the full pipeline (~90–180 GPU-seconds
        for Demucs + transcription; lighter steps run on cheap CPU).
      </p>

      <h2>Serverless GPU price ($/hour)</h2>
      <table className="cost">
        <thead>
          <tr><th>Provider</th><th>T4</th><th>L4</th><th>A10</th><th>L40S</th><th>A100-80GB</th><th>H100</th><th>Cold start</th></tr>
        </thead>
        <tbody>
          <tr><td>Modal</td><td>$0.59</td><td>$0.80</td><td>$1.10</td><td>$1.95</td><td>$2.50</td><td>$3.95</td><td>&lt;5 s</td></tr>
          <tr><td>RunPod (Flex)</td><td>—</td><td>~$0.39</td><td>~$0.44</td><td>~$0.86</td><td>~$1.39</td><td>~$4.18</td><td>5–20 s</td></tr>
          <tr><td>Replicate</td><td>$0.81</td><td>—</td><td>—</td><td>$3.51</td><td>$5.04</td><td>$5.49</td><td>~11 s</td></tr>
          <tr><td>fal.ai</td><td>—</td><td>—</td><td>—</td><td>—</td><td>$1.08</td><td>$1.80</td><td>~2–5 s</td></tr>
        </tbody>
      </table>

      <h2>Estimated cost per 3.5-min song</h2>
      <table className="cost">
        <thead><tr><th>Provider / GPU</th><th>$ per song</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>RunPod Flex · L4</td><td>~$0.01–0.02</td><td>cheapest; more DevOps (Docker images)</td></tr>
          <tr><td>Modal · L4 <strong>(recommended)</strong></td><td>~$0.02–0.04</td><td>best ergonomics for a custom pipeline; &lt;5 s cold start</td></tr>
          <tr><td>Modal · T4</td><td>~$0.015–0.03</td><td>budget; slower, fine for v1</td></tr>
          <tr><td>fal.ai · A100</td><td>~$0.03–0.05</td><td>faster wall-clock</td></tr>
        </tbody>
      </table>

      <h2>Monthly projection (Modal · L4, ~$0.03/song)</h2>
      <table className="cost">
        <thead><tr><th>Volume / month</th><th>Compute</th><th>+ Vercel/Supabase</th></tr></thead>
        <tbody>
          <tr><td>100 songs</td><td>~$3</td><td>free tiers</td></tr>
          <tr><td>1,000 songs</td><td>~$30</td><td>mostly free tiers</td></tr>
          <tr><td>10,000 songs</td><td>~$300</td><td>~$25–50 storage/egress</td></tr>
        </tbody>
      </table>

      <h2>Third-party stem APIs (no hosting, for comparison)</h2>
      <table className="cost">
        <thead><tr><th>Service</th><th>$/min audio</th><th>$/3.5-min song</th></tr></thead>
        <tbody>
          <tr><td>AudioShake (bulk)</td><td>$0.01–0.05</td><td>$0.04–0.18</td></tr>
          <tr><td>Music.ai (5-stem)</td><td>$0.07</td><td>~$0.25</td></tr>
          <tr><td>LALAL.AI</td><td>$0.06</td><td>~$0.21</td></tr>
          <tr><td>Moises Pro</td><td>~$0.10</td><td>~$0.35</td></tr>
        </tbody>
      </table>

      <p className="muted">
        Recommendation: build on <strong>Modal + L4</strong> for v1 (scale-to-zero, sub-5 s cold
        start, ~$0.02–0.04/song). Port to RunPod Flex if pure cost at scale becomes the priority.
        Self-hosting also gets you transcription + notation, which the stem APIs don&apos;t provide.
        Full sourcing in <code>docs/hosting-cost-chart.md</code>.
      </p>
    </>
  );
}
