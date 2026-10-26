"""Portable HTML + SVG output. Values and labels are escaped, no remote assets."""

from html import escape
import json
from pathlib import Path
from typing import Any

from .analysis import Lap


BLUE = "#1768b0"
ORANGE = "#ad4600"


def svg_chart(laps: tuple[Lap, Lap], field: str, title: str, unit: str, *, delta: bool = False) -> str:
    a, b = laps
    lo, hi = max(a.distances[0], b.distances[0]), min(a.distances[-1], b.distances[-1])
    xs = sorted({lo, hi, *[s.distance_m for lap in laps for s in lap.samples if lo <= s.distance_m <= hi]})
    if delta:
        series = [[(b.at(x, "elapsed_s") - b.at(lo, "elapsed_s")) - (a.at(x, "elapsed_s") - a.at(lo, "elapsed_s")) for x in xs]]
        colors = ["#5c409a"]
    else:
        series = [[lap.at(x, field) for x in xs] for lap in laps]
        colors = [BLUE, ORANGE]
    values = [value for row in series for value in row]
    low, high = min(values), max(values)
    padding = max((high - low) * .12, .1)
    low, high = low - padding, high + padding
    if field == "throttle_pct" and not delta:
        low, high = 0, 100
    def sx(x: float) -> float:
        return 75 + (x - lo) / (hi - lo) * 860
    def sy(y: float) -> float:
        return 225 - (y - low) / (high - low) * 165
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 280" role="img" aria-label="{escape(title, quote=True)}">',
              f'<title>{escape(title)} ({escape(unit)})</title>', '<rect width="1000" height="280" fill="#ffffff"/>',
              f'<text x="75" y="30" font-size="20">{escape(title)} ({escape(unit)})</text>']
    for i in range(5):
        value = low + (high - low) * i / 4
        y = sy(value)
        pieces += [f'<line x1="75" x2="935" y1="{y:.2f}" y2="{y:.2f}" stroke="#d4dbe5"/>',
                   f'<text x="64" y="{y+5:.2f}" text-anchor="end" font-size="13">{value:.1f}</text>']
    for i in range(6):
        value = lo + (hi - lo) * i / 5
        x = sx(value)
        pieces += [f'<text x="{x:.2f}" y="248" text-anchor="middle" font-size="13">{value:.0f}</text>']
    pieces += ['<text x="505" y="272" text-anchor="middle" font-size="14">같은 경로 기준 거리 (m)</text>']
    for values, color in zip(series, colors):
        points = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in zip(xs, values))
        pieces.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.8" stroke-linejoin="round"/>')
    if delta and low <= 0 <= high:
        pieces.append(f'<line x1="75" x2="935" y1="{sy(0):.2f}" y2="{sy(0):.2f}" stroke="#777" stroke-width="1"/>')
    pieces.append('</svg>')
    return "\n".join(pieces)


def observations(result: dict[str, Any]) -> list[str]:
    out = []
    for corner in result["corners"]:
        a, b = corner["reference"], corner["candidate"]
        change = b["exit_speed_kmh"] - a["exit_speed_kmh"]
        direction = "높습니다" if change >= 0 else "낮습니다"
        out.append(f'{corner["name"]}: 비교 랩의 +80m 지점 속도가 기준 랩보다 {abs(change):.1f}km/h {direction}. '
                   f'−70m~+80m 구간 시간 차이는 {corner["delta_passage_seconds"]:+.2f}초입니다. '
                   '원인 판단 전 진입·조향·가속 흐름과 주행 조건을 함께 확인하세요.')
    return out


def write_report(directory: Path, result: dict[str, Any], laps: dict[str, Lap], *, synthetic: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    a, b = (laps[result[key]] for key in ("reference_lap", "candidate_lap"))
    result = {**result, "synthetic_data": synthetic, "observations_ko": observations(result)}
    (directory / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    charts = []
    for filename, field, title, unit, delta in (
        ("speed", "speed_kmh", "속도", "km/h", False),
        ("throttle", "throttle_pct", "가속페달", "%", False),
        ("steering", "steering_deg", "조향각", "°", False),
        ("delta", "elapsed_s", "누적 시간 차이 · 비교 − 기준", "초", True),
    ):
        chart = svg_chart((a, b), field, title, unit, delta=delta)
        (directory / f"{filename}.svg").write_text(chart, encoding="utf-8")
        charts.append(chart)
    sectors = "".join(f'<tr><td>S{r["sector"]}</td><td>{r["start_m"]:.0f}–{r["end_m"]:.0f}m</td>'
                      f'<td>{r["reference_seconds"]:.2f}</td><td>{r["candidate_seconds"]:.2f}</td><td>{r["delta_seconds"]:+.2f}</td></tr>' for r in result["sectors"])
    corners = []
    for corner in result["corners"]:
        for label, key in ((a.name, "reference"), (b.name, "candidate")):
            row = corner[key]
            note = " · 창 경계 최저" if row["minimum_at_window_boundary"] else ""
            corners.append(f'<tr><td>{escape(corner["name"])}</td><td>{escape(label)}</td>'
                           f'<td>{row["entry_speed_kmh"]:.1f}</td><td>{row["window_min_speed_kmh"]:.1f}{note}</td>'
                           f'<td>{row["exit_speed_kmh"]:.1f}</td><td>{row["passage_time_seconds"]:.2f}</td></tr>')
    bullet_points = "".join(f"<li>{escape(text)}</li>" for text in result["observations_ko"])
    banner = "합성 데이터 데모 · 실차 성능 증거가 아닙니다" if synthetic else "사용자 입력의 오프라인 분석 · 경로 정렬 품질은 별도 확인 필요"
    html = f'''<!doctype html>
<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JEV 오프라인 비교</title><style>
body{{font-family:system-ui,sans-serif;color:#152235;background:#edf2f7;margin:0;line-height:1.65}}
main{{max-width:1100px;margin:auto;padding:24px}}section{{background:white;border-radius:14px;padding:22px;margin:18px 0}}
h1{{line-height:1.2}}h2{{margin-top:0}}.banner{{background:#fff0c4;padding:14px;border-radius:10px;font-weight:700}}
.legend{{display:flex;gap:24px;flex-wrap:wrap;font-weight:700}}.blue{{color:{BLUE}}}.orange{{color:{ORANGE}}}
svg{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-size:15px}}th,td{{padding:10px;border-bottom:1px solid #d4dbe5;text-align:left}}
.tablewrap{{overflow-x:auto}}.note{{color:#425570}}li{{margin:12px 0}}
</style><main><h1>JEV · 같은 위치에서 두 랩 비교</h1><div class="banner">{banner}</div>
<section><h2>비교 기준</h2><div class="legend"><span class="blue">● 기준 랩 {escape(a.name)} · 파랑 실선</span><span class="orange">● 비교 랩 {escape(b.name)} · 주황 실선</span></div>
<p>공통 경로 범위 {result["common_coverage_m"][0]:.0f}–{result["common_coverage_m"][1]:.0f}m. 섹터 합산 구간은 {result["comparison_interval_m"][0]:.0f}–{result["comparison_interval_m"][1]:.0f}m.</p>
<p class="note">이 예제는 이미 정렬된 거리 입력을 사용합니다. 영상 동기화·GPS 투영은 수행하지 않습니다. 음수 시간 차이는 비교 랩의 통과 시간이 짧다는 뜻입니다.</p></section>
<section><h2>위치별 그래프</h2>{''.join(charts)}</section>
<section><h2>섹터별 통과시간 · 초</h2><div class="tablewrap"><table><thead><tr><th>섹터</th><th>거리</th><th>기준</th><th>비교</th><th>비교 − 기준</th></tr></thead><tbody>{sectors}</tbody></table></div></section>
<section><h2>코너 분석 창의 속도 · km/h</h2><p class="note">진입 −70m / 최저 ±40m / 탈출 +80m. 공식 코너 경계나 에이펙스가 아닌 고정 분석 창입니다. 최저값이 창 경계이면 더 넓은 구간 검토가 필요합니다.</p>
<div class="tablewrap"><table><thead><tr><th>분석 구간</th><th>랩</th><th>−70m</th><th>±40m 최저</th><th>+80m</th><th>150m 통과 · 초</th></tr></thead><tbody>{''.join(corners)}</tbody></table></div></section>
<section><h2>관찰과 다음 확인</h2><ul>{bullet_points}</ul><p class="note">속도 차이만으로 제동·기어·그립·차량 제어의 원인을 확정하지 않습니다. 주행 중 조작 지시용이 아닙니다.</p></section>
<footer>JEV 오프라인 연구용 프로토타입 · 외부 통신·차량 접근·음성 합성 없음</footer></main></html>'''
    (directory / "index.html").write_text(html, encoding="utf-8")
