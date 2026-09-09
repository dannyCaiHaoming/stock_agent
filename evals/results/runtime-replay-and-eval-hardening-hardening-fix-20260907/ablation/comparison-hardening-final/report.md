# Multi-Agent Ablation 报告

- Ablation ID：`rreh-hardening-ablation-final-20260908`
- 代表案例：`4`
- 聚合结论：`NO_MEASURABLE_GAIN`

## 逐案例

### normal-research

- 可比性：`PASS`；结论：`NO_MEASURABLE_GAIN`
- cio-only: run_id=rreh-ablation-v3-normal-cio-only-20260907, trace=d696461ad33e9df8040455159d8f61ff76a23bf8a8517761aac4397ba696de08, eval=4c75c91f0255d0123b030e54436a3e00e690220328ed7c49142a45b1f5bf4455, quality=1.0, tokens=492906+3198, latency_ms=117418, telemetry=AVAILABLE
- analyst-cio: run_id=rreh-ablation-v3-normal-analyst-cio-20260907, trace=c3bec72ebdc5900254110bae8be58e83bc681d38afa44d82faad113e260fef4a, eval=07a466bb928556076ec49f4584dc5ae3396a03314d4f7fbdf2e4b2e08883853d, quality=1.0, tokens=768077+9481, latency_ms=251630, telemetry=AVAILABLE
- full-council: run_id=rreh-ablation-v3-normal-full-council-20260907, trace=ff223bdc066ceea006d2f563e273fa50a9a07142c77ffa30cf41173ef956030c, eval=141ccc91ab2ab36d7ee87febb4657592fb442c7a00c9e99c8d163adab0be90fc, quality=1.0, tokens=790413+13001, latency_ms=272331, telemetry=AVAILABLE

### insufficient-evidence

- 可比性：`PASS`；结论：`NO_MEASURABLE_GAIN`
- cio-only: run_id=rreh-hardening-ablation-insufficient-cio-only-v2-20260908, trace=bb23e800ebee9590db95ea8fbc1966b48decfbb951b6df4840be077004ad7eb2, eval=c7bc89d727c33df1cf38090f40304321b44dd1edad746126de3f3ce239861afa, quality=1.0, tokens=289980+2838, latency_ms=88904, telemetry=AVAILABLE
- analyst-cio: run_id=rreh-hardening-ablation-insufficient-analyst-cio-v3-20260908, trace=29ba3371b41607a5251214e34cbbf3dd1cada25ba363585e8f409b638f3bbafb, eval=162c1601e5c4e2173ae2bb786d727e8ecfcdd4151a88c3a40cc5ce331c437df9, quality=1.0, tokens=595823+8140, latency_ms=207523, telemetry=AVAILABLE
- full-council: run_id=rreh-hardening-ablation-insufficient-full-council-v8-20260908, trace=9b5c91b27fc99409b0554a5d3703ec0bc045bbd644f840e382f9c3e9ac3db991, eval=d4749929947f19a7d9c575c7cec6cd7f274e5effad5c3eacc8e5ae61f81a7410, quality=1.0, tokens=807412+12135, latency_ms=256052, telemetry=AVAILABLE

### analyst-skeptic-strong-conflict

- 可比性：`PASS`；结论：`NO_MEASURABLE_GAIN`
- cio-only: run_id=rreh-hardening-ablation-conflict-cio-only-v5-20260908, trace=518fd37058740b7f1498de1d0bd5327e54a7636c3d93bfbdca23588f7fcabe7a, eval=83990b73ff303b97ad24a140c2393d378b4267ed6d296d23a15e33203c9ca874, quality=1.0, tokens=331461+3867, latency_ms=111440, telemetry=AVAILABLE
- analyst-cio: run_id=rreh-hardening-ablation-conflict-analyst-cio-v4-20260908, trace=3c4da519fc51e2f7897e2ca76beb4254d6154c5451dabd30b84af94645fb8056, eval=6264e037fbe756fcc27c8574b91a4e16335274680d1516140116ac2bfcfede3a, quality=1.0, tokens=543653+9107, latency_ms=243659, telemetry=AVAILABLE
- full-council: run_id=rreh-hardening-ablation-conflict-full-council-v3-20260908, trace=89e12f44792b5565c3058023df971ed5b3ce7abc3aeae6d78df9254480249898, eval=8b903c023879faf9f22b0376bc875b29b8b3438aee519fb2ffcea39ce68aa0e3, quality=1.0, tokens=1006714+13840, latency_ms=263880, telemetry=AVAILABLE

### mandatory-no-trade

- 可比性：`PASS`；结论：`NO_MEASURABLE_GAIN`
- cio-only: run_id=rreh-ablation-v3-mandatory-cio-only-20260907, trace=ce7a7ba697c597e16d39d1edaf8535827b9258166c2dbb2c1e9695f7a1c0570b, eval=8fd752b67b49a71788644ecee3715a7b8e5e5a57dcd8c64589ae07663ae7091c, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- analyst-cio: run_id=rreh-ablation-v3-mandatory-analyst-cio-20260907, trace=96b21651486731d2415eec8ae29f0905eb447e183645d6e42915f3bf1f09862f, eval=870c4c119efa3644d9610fdcd3b81e0c4672b96c4752cc474c26c4fca908f414, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- full-council: run_id=rreh-ablation-v3-mandatory-full-council-20260907, trace=584c5f2ddf9a49c8ab12b88fc72c12a961566f31af0048e91fb9e4c15a022638, eval=9a6de28c48756467f7e1a5704f702093854d20bc6e7ec6375ff61d7faf3e7111, quality=None, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY

## 聚合 Profile

- cio-only: quality=1.0, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- analyst-cio: quality=1.0, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY
- full-council: quality=1.0, tokens=None+None, latency_ms=None, telemetry=MISSING_TELEMETRY

## Reason Codes

- `NO_MEASURABLE_GAIN`
