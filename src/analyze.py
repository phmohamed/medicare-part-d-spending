"""Medicare Part D spending by drug, 2020-2024 (CMS). SQL for the questions, pandas/matplotlib/plotly for the output."""
import sqlite3, pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots

raw = pd.read_csv("data/part_d_spending_by_drug_2024.csv")
YRS = [2020, 2021, 2022, 2023, 2024]
con = sqlite3.connect("data/partd.db")
# brand-level rows ("Overall") and manufacturer-level rows are two views of the same spending
brand = raw[raw.Mftr_Name == "Overall"].copy()
mfr = raw[raw.Mftr_Name != "Overall"].copy()
# CMS has no brand/generic flag. Rough proxy: a product counts as generic-type when its name equals the generic
# name, or when more than one manufacturer sells it. Known flaws: authorized generics and biosimilar-linked
# products (for example Humira's second labeller) get misfiled. Treat the shares as approximate.
same = brand.Brnd_Name.str.lower().str.strip() == brand.Gnrc_Name.str.lower().str.strip()
brand["is_brand"] = (~(same | (brand.Tot_Mftr > 1))).astype(int)
brand.to_sql("brand", con, if_exists="replace", index=False)
mfr.to_sql("mfr", con, if_exists="replace", index=False)
print("brand rows", len(brand), "manufacturer rows", len(mfr))
tot = {y: brand[f"Tot_Spndng_{y}"].sum() for y in YRS}
print({y: round(v/1e9, 1) for y, v in tot.items()})

def q(name, sql):
    d = pd.read_sql(sql, con); d.to_csv(f"data/sql_{name}.csv", index=False); print("\n", name); print(d.head(12).to_string(index=False)); return d

top = q("top_drugs_2024", """
SELECT Brnd_Name, Gnrc_Name, ROUND(Tot_Spndng_2024/1e9,2) spend_bn_2024, ROUND(Tot_Spndng_2020/1e9,2) spend_bn_2020,
       ROUND(100.0*Tot_Spndng_2024/(SELECT SUM(Tot_Spndng_2024) FROM brand),2) pct_of_total, Tot_Clms_2024 claims_2024,
       ROUND(Avg_Spnd_Per_Clm_2024,0) spend_per_claim
FROM brand ORDER BY Tot_Spndng_2024 DESC LIMIT 25""")
bg = q("brand_vs_generic", """
SELECT CASE is_brand WHEN 1 THEN 'brand' ELSE 'generic-type (rough proxy)' END kind, COUNT(*) products,
       ROUND(SUM(Tot_Spndng_2024)/1e9,1) spend_bn, ROUND(SUM(Tot_Clms_2024)/1e6,0) claims_m,
       ROUND(100.0*SUM(Tot_Spndng_2024)/(SELECT SUM(Tot_Spndng_2024) FROM brand),1) pct_spend,
       ROUND(100.0*SUM(Tot_Clms_2024)/(SELECT SUM(Tot_Clms_2024) FROM brand),1) pct_claims,
       ROUND(SUM(Tot_Spndng_2024)/SUM(Tot_Clms_2024),0) spend_per_claim
FROM brand GROUP BY is_brand""")
mf = q("top_manufacturers_2024", """
SELECT Mftr_Name, COUNT(*) products, ROUND(SUM(Tot_Spndng_2024)/1e9,2) spend_bn,
       ROUND(100.0*SUM(Tot_Spndng_2024)/(SELECT SUM(Tot_Spndng_2024) FROM mfr),2) pct_of_total
FROM mfr GROUP BY Mftr_Name ORDER BY SUM(Tot_Spndng_2024) DESC LIMIT 20""")
gr = q("fastest_growing_2020_2024", """
SELECT Brnd_Name, Gnrc_Name, ROUND(Tot_Spndng_2020/1e9,2) spend_bn_2020, ROUND(Tot_Spndng_2024/1e9,2) spend_bn_2024,
       ROUND(Tot_Spndng_2024/Tot_Spndng_2020,1) growth_x, ROUND(Tot_Spndng_2024-Tot_Spndng_2020)/1e9 added_bn
FROM brand WHERE Tot_Spndng_2020 >= 5e8 AND Tot_Spndng_2024 IS NOT NULL ORDER BY added_bn DESC LIMIT 15""")
pr = q("biggest_price_moves", """
SELECT Brnd_Name, Gnrc_Name, ROUND(Avg_Spnd_Per_Dsg_Unt_Wghtd_2020,2) per_unit_2020, ROUND(Avg_Spnd_Per_Dsg_Unt_Wghtd_2024,2) per_unit_2024,
       ROUND(100*CAGR_Avg_Spnd_Per_Dsg_Unt_20_24,1) cagr_pct, ROUND(Tot_Spndng_2024/1e9,2) spend_bn_2024
FROM brand WHERE Tot_Spndng_2024 >= 1e9 AND Tot_Spndng_2020 >= 1e8 ORDER BY CAGR_Avg_Spnd_Per_Dsg_Unt_20_24 DESC LIMIT 12""")

# diabetes drug classes by generic-name keywords (simple, visible, easy to change)
CLASSES = {"GLP-1 / GIP (semaglutide, tirzepatide, dulaglutide, liraglutide)": ["semaglutide", "tirzepatide", "dulaglutide", "liraglutide", "exenatide"],
           "SGLT2 (empagliflozin, dapagliflozin, canagliflozin)": ["empagliflozin", "dapagliflozin", "canagliflozin", "ertugliflozin"],
           "DPP-4 (sitagliptin, linagliptin, saxagliptin, alogliptin)": ["sitagliptin", "linagliptin", "saxagliptin", "alogliptin"],
           "Insulins": ["insulin"],
           "Metformin alone": ["metformin hcl"]}
rows = []
for name, keys in CLASSES.items():
    m = brand.Gnrc_Name.str.lower().apply(lambda g: any(k in g for k in keys) and ("/" not in g if name.startswith("Metformin") else True))
    rows.append({"class": name, **{f"spend_bn_{y}": brand.loc[m, f"Tot_Spndng_{y}"].sum() / 1e9 for y in YRS}})
cls = pd.DataFrame(rows).round(2); cls.to_csv("data/diabetes_classes.csv", index=False); print("\n", cls.to_string(index=False))

# ---- charts -----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 7)); t = top.head(15).iloc[::-1]
ax.barh(t.Brnd_Name, t.spend_bn_2024, color="#2a7f9e"); ax.set_xlabel("2024 Part D spending, $ billion")
for i, v in enumerate(t.spend_bn_2024): ax.text(v + 0.1, i, f"{v:.1f}", va="center", fontsize=8)
ax.set_title("Top 15 drugs by Medicare Part D spending, 2024"); plt.tight_layout(); plt.savefig("figures/top15_spend_2024.png", dpi=150); plt.close()

fig, ax = plt.subplots(figsize=(9, 5.5))
for name in ["Ozempic", "Mounjaro", "Jardiance", "Trulicity", "Eliquis", "Farxiga", "Januvia"]:
    r = brand[brand.Brnd_Name == name].iloc[0]
    ax.plot(YRS, [r[f"Tot_Spndng_{y}"] / 1e9 for y in YRS], marker="o", label=name)
ax.set_ylabel("$ billion"); ax.set_xticks(YRS); ax.legend(); ax.set_title("Diabetes and heart drugs, Part D spending 2020-2024\n(Mounjaro starts in 2022, when it launched)")
plt.tight_layout(); plt.savefig("figures/diabetes_trends.png", dpi=150); plt.close()

fig, axs = plt.subplots(1, 2, figsize=(10, 4.5)); b = bg.set_index("kind")
axs[0].bar(b.index.str[:7], b.pct_claims, color=["#2a7f9e", "#e0a030"]); axs[0].set_title("Share of claims (%)")
axs[1].bar(b.index.str[:7], b.pct_spend, color=["#2a7f9e", "#e0a030"]); axs[1].set_title("Share of spending (%)")
for ax in axs:
    for i, v in enumerate(ax.patches): ax.text(v.get_x() + v.get_width() / 2, v.get_height() + 1, f"{v.get_height():.0f}", ha="center")
    ax.set_ylim(0, 100)
fig.suptitle("Brand vs generic in Part D, 2024"); plt.tight_layout(); plt.savefig("figures/brand_vs_generic.png", dpi=150); plt.close()

fig, ax = plt.subplots(figsize=(9, 6)); m = mf.head(15).iloc[::-1]
ax.barh(m.Mftr_Name, m.spend_bn, color="#6a4c93"); ax.set_xlabel("2024 Part D spending, $ billion"); ax.set_title("Top manufacturers by Part D spending, 2024\n(manufacturer names as truncated in the CMS file)")
plt.tight_layout(); plt.savefig("figures/top_manufacturers_2024.png", dpi=150); plt.close()

# ---- interactive dashboard --------------------------------------------------
d = brand[(brand.Tot_Spndng_2024 >= 2e8) & brand.Tot_Spndng_2020.notna()].copy()
d["growth"] = d.Tot_Spndng_2024 / d.Tot_Spndng_2020
f = make_subplots(rows=2, cols=2, subplot_titles=("Top 20 drugs, 2024 ($bn)", "Brand vs generic share, 2024 (%)", "Spend 2020 vs 2024 ($bn, log axes)", "Top 15 manufacturers, 2024 ($bn)"),
                  specs=[[{}, {}], [{}, {}]])
t20 = top.head(20).iloc[::-1]
f.add_trace(go.Bar(y=t20.Brnd_Name, x=t20.spend_bn_2024, orientation="h", name="2024 spend"), 1, 1)
f.add_trace(go.Bar(x=["claims", "spending"], y=[b.loc[b.index.str.startswith("brand"), "pct_claims"].iloc[0], b.loc[b.index.str.startswith("brand"), "pct_spend"].iloc[0]], name="brand"), 1, 2)
f.add_trace(go.Bar(x=["claims", "spending"], y=[b.loc[b.index.str.startswith("generic"), "pct_claims"].iloc[0], b.loc[b.index.str.startswith("generic"), "pct_spend"].iloc[0]], name="generic"), 1, 2)
f.add_trace(go.Scatter(x=d.Tot_Spndng_2020 / 1e9, y=d.Tot_Spndng_2024 / 1e9, mode="markers", text=d.Brnd_Name, name="drug (>= $0.2bn in 2024)"), 2, 1)
f.add_trace(go.Bar(y=mf.head(15).Mftr_Name[::-1], x=mf.head(15).spend_bn[::-1], orientation="h", name="manufacturer"), 2, 2)
f.update_xaxes(type="log", row=2, col=1); f.update_yaxes(type="log", row=2, col=1)
f.update_layout(height=900, title="Medicare Part D spending by drug, 2020-2024 (CMS public data)", barmode="group", showlegend=True)
f.write_html("dashboard.html", include_plotlyjs="cdn")
