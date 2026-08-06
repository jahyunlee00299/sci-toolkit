# Publication Figures — recurring patterns

A multi-panel manuscript figure rebuild (5 main + 12 SI) surfaced the patterns below repeatedly.
참조 스크립트 위치(예시): `<your library path>/<paper>/submissions/<Journal>/figures/`

---

## Pattern 1: Errorbar cap을 marker 위에 올리기

**When to use:** datapoint가 dense하거나 marker가 커서 cap이 가려질 때.

`plot()`과 `errorbar(fmt="none")`을 분리하고 errorbar를 높은 zorder로 올린다.
ecolor는 species color 대신 `"#222222"` 권장 (dense 배경에서 더 명확).

```python
ax.plot(x, y, marker="o", color=color, zorder=3)
ax.errorbar(x, y, yerr=yerr, fmt="none",
            ecolor="#222222", capsize=4, capthick=1.1,
            elinewidth=1.1, zorder=5)
```

참조 예시: `fig_S1_enzyme_activity/script.py`

---

## Pattern 2: 3D surface RSM colorbar 위치

**When to use:** 3D surface subplot 2-panel에서 colorbar가 z축에 바짝 붙어야 할 때.

```python
cb = fig.colorbar(surf, ax=ax, pad=0.10, shrink=0.55, aspect=18)
fig.subplots_adjust(wspace=-0.05)
```

참조 예시: `fig_1_response_surface/script.py`

---

## Pattern 3: Sobol/bar 차트 errorbar cap 스타일

**When to use:** 민감도 분석(Sobol) 또는 bar chart에서 명확한 errorbar cap이 필요할 때.

```python
ax.bar(x, height, yerr=err,
       capsize=4, error_kw=dict(capthick=1.1, elinewidth=1.1, ecolor="#222222"))
```

참조 예시: `fig_2_sensitivity/script.py`

---

## Pattern 4: Scatter + text label 충돌 회피

**When to use:** scatter plot에 항목별 텍스트 라벨을 붙일 때 겹침 방지.

`LABEL_OFFSET` dict에 `(dx, dy_factor, ha)` 튜플 부여. 4방향(좌상/좌하/우상/우하) 분산.
fontsize 7.5–8.5 pt.

```python
LABEL_OFFSET = {
    "item_A": (-0.15,  0.04, "right"),
    "item_B": ( 0.10, -0.06, "left"),
    "item_C": ( 0.10,  0.04, "left"),
}
for name, (x, y) in data.items():
    dx, dy_f, ha = LABEL_OFFSET.get(name, (0.10, 0.04, "left"))
    ax.text(x + dx, y + dy_f * y_range, name, ha=ha, fontsize=8)
```

참조 예시: `fig_S2_green_metrics/script.py`

---

## Pattern 5: Fit line 외삽 (extrapolation) 표시

**When to use:** thermal inactivation 등 trend를 xlim 전체 범위로 보여야 할 때.

per-enzyme 데이터 범위로 clip하지 말고 xlim 전체로 그린다. y범위는 `set_ylim`으로 reference에 맞춤.

```python
x_fit = np.linspace(*ax.get_xlim(), 200)
ax.plot(x_fit, model(x_fit, *popt), "-", color=color, lw=1.2, zorder=2)
ax.set_ylim(y_lo, y_hi)
```

참조 예시: `fig_S3_stability/script.py`

---

## Pattern 6: EF metric 단위 표기

**When to use:** E-factor, mass-based green metric 표기 시.

`g g⁻¹` (superscript) 대신 `g/g` slash 형식 사용.
축 라벨/colorbar 라벨/범례 모두 동일 적용.

```python
ax.set_ylabel("E-factor (g/g)")
cb.set_label("sEF (g/g)")
```

참조: slash 단위 규칙 (academic-term-rules §8).

---

## Pattern 7: Subplot title 단순화

**When to use:** 다패널 figure에서 panel title이 캡션과 중복될 때.

enzyme명/substrate명 등 텍스트 제거, panel letter(a/b/c…)만 남긴다.

```python
ax.set_title("a", fontsize=11, fontweight="bold", loc="left")
```

캡션에서 상세 설명 제공. 참조 예시: `fig_S4_residuals/script.py`, `fig_S5_obs_pred/script.py`
