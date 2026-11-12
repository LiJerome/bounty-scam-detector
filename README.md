# bounty-scam-detector

**给 GitHub 上的「悬赏仓库」打分，在你浪费一整天之前告诉你：这笔钱大概率不存在。**

---

## 为什么写这个

2026 年 11 月，我想找点开源赏金做。抓了一遍 GitHub 上所有 open 状态的 bounty issue，
结果发现一个难看的事实：

**公开可见、随手可捡的悬赏，基本已经是空的了。**

不是没人付钱，而是：

- 真悬赏一挂出来几小时内被抢走，轮不到路过的人
- 留在公开列表里的大头，是**诱捕自动化 Agent 的测试夹具**
- 和**用积分兑换当幌子的免费劳动力农场**

举三个我实际抓到的例子（数据抓取于 2026-11-12）：

| 仓库 | 数据 | 说明 |
|---|---|---|
| `tine1117/oss-hunter-livefire` | 6 KB 代码，154 个 open issue | 简介原文：*"Sandbox fixture for testing an automated OSS bounty-solving workflow"* |
| `PhanKhoa95/oss-bot-trap-benchmark` | 0 star / 17 fork / 74 issue，建库 5 天 | 简介原文：*"automated contributor telemetry benchmark"*，issue 里还埋了验证 token |
| `WillSmithTE/qdrant-qdrant` | `fork=true`，0 star，395 个 issue | 把知名向量库 qdrant 整个 fork 一份，挂上假悬赏 |
| `zhangjiayang6835-cyber/bounty-plaza` | 13 star 却有 149 fork、1462 个 issue | 发钱公式 `赏金 × 1.25 × R × 0.72`，凭空乘 1.25 再给你 95% |

最讽刺的是第一个——它自己承认是"测试夹具"。

## 它是怎么判断的

六条信号，每条都能直接验证，不靠玄学：

| # | 信号 | 分值 | 为什么有效 |
|---|---|---|---|
| 1 | `fork` 数超过 `star` 数（且 star < 100） | 30 | 正常项目一定反过来。fork 远多于 star，说明 fork 是为了提交 PR 产生的，不是有人用 |
| 2 | open issue > 100 但代码 < 2000 KB | 30 | 6 KB 代码挂 154 个 issue，这些 issue 不可能是真需求 |
| 3 | 建库 ≤ 60 天就挂了 > 50 个 issue | 25 | 真实项目长不出这个速度 |
| 4 | 简介/仓库名含 `benchmark`、`fixture`、`sandbox`、`telemetry`、`trap` 等 | 40 | 作者自己说了 |
| 5 | 是别人的 `fork`，却挂着大量 issue | 35 | fork 一份知名项目来挂悬赏，是最省事的骗法 |
| 6 | 0 star 却有 ≥ 20 个 fork | 25 | 幽灵仓库 |

总分 ≥ 60 判 `HIGH`，≥ 30 判 `MEDIUM`。

## 用法

无第三方依赖，Python 3.8+ 直接跑：

```bash
# 查几个具体仓库
python detector.py tine1117/oss-hunter-livefire ClankerNation/OpenAgents

# 搜出当前所有 open 的 bounty issue，按仓库聚合后统一打分
python detector.py --search "label:bounty"

# 带上全部命中理由
python detector.py --search "label:bounty" --details

# 机器可读
python detector.py --search "label:bounty" --json
```

设 `GITHUB_TOKEN` 环境变量能把 API 配额从 60 次/小时提到 5000：

```bash
export GITHUB_TOKEN=ghp_xxx
```

## 输出长什么样

拿 5 个已知的陷阱仓库 + 2 个正常项目做对照，实跑结果：

```
仓库                                              分  风险     主要理由
--------------------------------------------------------------------------------------------------------
tine1117/oss-hunter-livefire                  100  HIGH   fork(167) 超过 star(27)
PhanKhoa95/oss-bot-trap-benchmark              95  HIGH   fork(17) 超过 star(0)
WillSmithTE/qdrant-qdrant                      65  HIGH   fork(8) 超过 star(0)
zhangjiayang6835-cyber/bounty-plaza            60  HIGH   fork(149) 超过 star(13)
ClankerNation/OpenAgents                       60  HIGH   fork(144) 超过 star(15)
qdrant/qdrant                                   0  LOW    无明显异常
calcom/cal.com                                  0  LOW    无明显异常
--------------------------------------------------------------------------------------------------------
共 7 个仓库，其中 5 个高风险。
```

加 `--details` 会给出每一条命中理由：

```
tine1117/oss-hunter-livefire  (100 分)
   · fork(167) 超过 star(27)
   · 154 个 open issue，代码只有 6 KB
   · 自述含「fixture」

WillSmithTE/qdrant-qdrant  (65 分)
   · fork(8) 超过 star(0)
   · 是别人的 fork，却挂着大量 issue

zhangjiayang6835-cyber/bounty-plaza  (60 分)
   · fork(149) 超过 star(13)
   · 1462 个 open issue，代码只有 132 KB
```

**5 个陷阱全部判 HIGH，2 个正常项目全部 0 分。** 对照组的作用就在这里——
如果分数只会往高走，那它就不是检测器，只是个吵架工具。

## 它做不到什么

- **只能判断「仓库可疑」，不能证明「这个悬赏是假的」。** 一个真项目也可能因为刚开源而有奇怪的指标。分数是线索，不是判决。
- **不判断悬赏金额是否真实托管。** 这事只有平台能证明，代码看不出。
- 不覆盖平台内部的悬赏（Algora 控制台、Code4rena 之类），那些只能登录看。

## 更保守的建议

如果你只是想要钱，别在这些地方找。真实建议：

1. **能收到人民币的渠道**优先——本地服务、熟人生意、国内平台
2. **开源赏金当彩票，不当工资**
3. 任何"高额悬赏 + 零门槛 + 长期没人领"的组合，先假设它是假的

## License

MIT
