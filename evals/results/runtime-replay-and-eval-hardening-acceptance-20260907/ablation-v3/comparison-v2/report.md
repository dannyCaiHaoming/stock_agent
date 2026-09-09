# Multi-Agent Ablation 报告

- Ablation ID：`rreh-ablation-v3-final-20260907`
- 代表案例：`4`
- 聚合结论：`NOT_COMPARABLE`

## 逐案例

### normal-research

- 可比性：`PASS`；结论：`NO_MEASURABLE_GAIN`
- cio-only: run_id=rreh-ablation-v3-normal-cio-only-20260907, trace=d696461ad33e9df8040455159d8f61ff76a23bf8a8517761aac4397ba696de08, eval=ce6d20e4b3d19cff53e7856b4e0e4225d6b61945c062f32395c34057704a3beb, quality=1.0, tokens=492906+3198, latency_ms=117418, telemetry=AVAILABLE
- analyst-cio: run_id=rreh-ablation-v3-normal-analyst-cio-20260907, trace=c3bec72ebdc5900254110bae8be58e83bc681d38afa44d82faad113e260fef4a, eval=94dfd2d0efb47f42b6b674c998fc223046f80b95cfd48b2a687ae477c77abcb2, quality=0.8333333333333334, tokens=768077+9481, latency_ms=251630, telemetry=AVAILABLE
- full-council: run_id=rreh-ablation-v3-normal-full-council-20260907, trace=ff223bdc066ceea006d2f563e273fa50a9a07142c77ffa30cf41173ef956030c, eval=7a0ca36299680409541e1a78702c4fba0d1aadb4e1c52984257ee065e7f9d3a5, quality=1.0, tokens=790413+13001, latency_ms=272331, telemetry=AVAILABLE

### insufficient-evidence

- 可比性：`PASS`；结论：`NOT_COMPARABLE`
- cio-only: run_id=rreh-ablation-v3-insufficient-cio-only-20260907, trace=8664d2810bfb93bed0b377bef23eb3612f12641c6abc5ec82e02c9d17059dd13, eval=f312d52fb6d158f7434ab43a9b7f29c8451c7841269cdab7ce312833a51dd1a2, quality=1.0, tokens=622795+3973, latency_ms=132355, telemetry=AVAILABLE
- analyst-cio: run_id=rreh-ablation-v3-insufficient-analyst-cio-rerun-20260907, trace=6533e772cae4fe2871b3041dcb5271742a3d80595e0e53cb4c7860d248ffc140, eval=ff7a8fdc3dc9a2cb112dc2d385b3eccc3b4f1fc754d2a291e7ee27c40be7405c, quality=0.8333333333333334, tokens=556296+7651, latency_ms=204387, telemetry=AVAILABLE
- full-council: run_id=rreh-ablation-v3-insufficient-full-council-20260907, trace=53fbbd42eb9304decaff84a24c2a207b5a58e755755aa0b374662d8d2c7fad8b, eval=2afd04b9ac0242001968a74ce3c5252c9c6d3e6f4d1ac8c8c68e841e6441b4f9, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY

### analyst-skeptic-strong-conflict

- 可比性：`PASS`；结论：`NOT_COMPARABLE`
- cio-only: run_id=rreh-ablation-v3-conflict-cio-only-20260907, trace=c4a39b25be3826e8b424610107bb2ff74595b1df098fd8e1f246b38594b9b73d, eval=4634153da517afcb0d9a18d521a401b142270c095a17611211290dbb2677666f, quality=1.0, tokens=323683+3197, latency_ms=99001, telemetry=AVAILABLE
- analyst-cio: run_id=rreh-ablation-v3-conflict-analyst-cio-rerun-20260907, trace=4b14019ec304c22df54747c779ffdd8afc5ac864107c3f572a76d310699c40b5, eval=c5125594d372bf62e9fadba1cee06f8fe02135d81ce803a1b9bd579a51fbb92f, quality=1.0, tokens=656936+8395, latency_ms=241762, telemetry=AVAILABLE
- full-council: run_id=rreh-ablation-v3-conflict-full-council-20260907, trace=4e9f6d48276e295c6c70be78748dc2a0444401c6b88b8a65341e44eb1055c47e, eval=8b9f24f09f996b9e5b4796eacada8bf4ae4f06ea901d214da31da106c6417143, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY

### mandatory-no-trade

- 可比性：`PASS`；结论：`NOT_COMPARABLE`
- cio-only: run_id=rreh-ablation-v3-mandatory-cio-only-20260907, trace=ce7a7ba697c597e16d39d1edaf8535827b9258166c2dbb2c1e9695f7a1c0570b, eval=0ac047ebd20d127346a3435f2341481c9ef115311bfb0e1f90c643d726d22261, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- analyst-cio: run_id=rreh-ablation-v3-mandatory-analyst-cio-20260907, trace=96b21651486731d2415eec8ae29f0905eb447e183645d6e42915f3bf1f09862f, eval=844c7a0aa148028f981a37035c1ac299d2a0c4d5a45a95a1797ae0ebbf2ff461, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- full-council: run_id=rreh-ablation-v3-mandatory-full-council-20260907, trace=584c5f2ddf9a49c8ab12b88fc72c12a961566f31af0048e91fb9e4c15a022638, eval=409b7436637b161c9909c1db5785fe7c5faf0fd8e3c6d003da6cf48b0251a5a5, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY

## 聚合 Profile

- cio-only: quality=1.0, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- analyst-cio: quality=0.888888888888889, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- full-council: quality=1.0, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY

## Reason Codes

- `ABLATION_CASE_NOT_COMPARABLE:insufficient-evidence`
- `ABLATION_CASE_NOT_COMPARABLE:analyst-skeptic-strong-conflict`
- `ABLATION_CASE_NOT_COMPARABLE:mandatory-no-trade`
