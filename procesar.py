#!/usr/bin/env python3
"""
Procesa datos_crudos.txt → limpia, entrena modelo TinyML, genera modelo.h
Soporta formato DNS: dns_qty, unique, new
Clases: background(0), foreground(1), sospechoso(2)
"""

import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import re, os
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

RAW_FILE = "datos_crudos.txt"
CSV_FILE = "dataset.csv"
MODEL_H = "modelo.h"

LABEL_MAP = {
    "background": 0,
    "foreground": 1,
    "sospechoso": 2,
}
LABEL_NAMES = ["background", "foreground", "sospechoso"]

FEAT = ["dns_qty", "dns_unique", "dns_new"]

# ── 1. PARSING ──────────────────────────────────────────────────────

def parse(raw):
    rows = []
    for line in raw.splitlines():
        m = re.search(r'\[W\] dns_qty=(\d+) unique=(\d+) new=(\d+).*label=(\S+)', line)
        if not m:
            continue
        qty, uniq, nw, label = m.groups()
        if label not in LABEL_MAP:
            continue
        rows.append({
            "dns_qty": int(qty),
            "dns_unique": int(uniq),
            "dns_new": int(nw),
            "label": label,
            "y": LABEL_MAP[label],
        })
    return pd.DataFrame(rows)

# ── 2. FILTRO ───────────────────────────────────────────────────────

def filtrar(df):
    print(f"  Total ventanas: {len(df)}")
    for lbl in LABEL_NAMES:
        c = (df.label == lbl).sum()
        print(f"    {lbl}: {c}")

    df = df[df.label != "unlabeled"].copy()

    # En DNS, el background casi siempre es qty=0 o 1
    # Si foreground tiene qty=0 es probable background
    dudosos = (df.label == "foreground") & (df.dns_qty == 0)
    print(f"  Foreground dudosas (qty=0): {dudosos.sum()} — se descartan")
    df = df[~dudosos].copy()

    # Si sospechoso tiene qty=0 o 1, también dudoso
    dudosos2 = (df.label == "sospechoso") & (df.dns_qty <= 1)
    print(f"  Sospechoso dudosas (qty<=1): {dudosos2.sum()} — se descartan")
    df = df[~dudosos2].copy()

    print(f"  Ventanas utiles: {len(df)}")
    for lbl in LABEL_NAMES:
        c = (df.label == lbl).sum()
        print(f"    {lbl}: {c}")
    return df

# ── 3. ENTRENAR ────────────────────────────────────────────────────

def entrenar(df):
    X = df[FEAT].values
    y = df["y"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    dt = DecisionTreeClassifier(max_depth=4, random_state=42, class_weight="balanced")
    dt.fit(X_train, y_train)

    rf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42, class_weight="balanced")
    rf.fit(X_train, y_train)

    print("\n--- Decision Tree ---")
    y_pred = dt.predict(X_test)
    print(classification_report(y_test, y_pred, target_names=LABEL_NAMES))
    cm = confusion_matrix(y_test, y_pred)
    print(f"  Matriz de confusion:\n{cm}")

    print("\n--- Random Forest (referencia) ---")
    y_pred_rf = rf.predict(X_test)
    print(classification_report(y_test, y_pred_rf, target_names=LABEL_NAMES))

    print("\n--- Arbol de decision ---")
    print(export_text(dt, feature_names=FEAT))

    return dt

# ── 4. EXPORTAR modelo.h ──────────────────────────────────────────

def exportar_c(dt):
    tree = dt.tree_
    n_nodes = tree.node_count
    children_left = tree.children_left
    children_right = tree.children_right
    feature = tree.feature
    threshold = tree.threshold
    value = tree.value

    SCALE = 100

    lines = []
    lines.append("#ifndef MODELO_H")
    lines.append("#define MODELO_H")
    lines.append("")
    lines.append("/* Generado por procesar.py -- Arbol TinyML */")
    lines.append("/* Features: " + ", ".join(FEAT) + " */")
    lines.append("/* Clases: 0=background, 1=foreground, 2=sospechoso */")
    lines.append("")
    lines.append("#define N_FEATURES " + str(len(FEAT)))
    lines.append("")

    lines.append("enum feature {")
    for i, name in enumerate(FEAT):
        lines.append(f"    FEAT_{name.upper()} = {i},")
    lines.append("};")
    lines.append("")

    lines.append("typedef struct {")
    lines.append("    int16_t feature;")
    lines.append("    int16_t threshold;")
    lines.append("    int16_t left;")
    lines.append("    int16_t right;")
    lines.append("    int16_t prediction;")
    lines.append("} Node;")
    lines.append("")

    nodes = []
    for i in range(n_nodes):
        if children_left[i] == -1:
            pred = int(np.argmax(value[i][0]))
            nodes.append({"feature": -1, "threshold": 0, "left": -1, "right": -1, "prediction": pred})
        else:
            th = int(threshold[i] * SCALE)
            nodes.append({"feature": int(feature[i]), "threshold": th, "left": int(children_left[i]), "right": int(children_right[i]), "prediction": -1})

    lines.append("static const Node tree[" + str(n_nodes) + "] = {")
    for node in nodes:
        lines.append(f"    {{{node['feature']}, {node['threshold']}, {node['left']}, {node['right']}, {node['prediction']}}},")
    lines.append("};")
    lines.append("")

    lines.append("static inline int predecir(const int32_t *features) {")
    lines.append("    int idx = 0;")
    lines.append("    while (1) {")
    lines.append("        if (tree[idx].feature < 0)")
    lines.append("            return tree[idx].prediction;")
    lines.append("        if (features[tree[idx].feature] <= tree[idx].threshold)")
    lines.append("            idx = tree[idx].left;")
    lines.append("        else")
    lines.append("            idx = tree[idx].right;")
    lines.append("    }")
    lines.append("}")
    lines.append("")
    lines.append("#endif /* MODELO_H */")

    return "\n".join(lines)

# ── MAIN ─────────────────────────────────────────────────────────

def main():
    if not os.path.exists(RAW_FILE):
        print(f"ERROR: No se encuentra {RAW_FILE}")
        sys.exit(1)

    print(f"Leyendo {RAW_FILE}...")
    with open(RAW_FILE) as f:
        raw = f.read()

    df = parse(raw)
    if len(df) == 0:
        print("No se encontraron ventanas [W] en el archivo.")
        sys.exit(1)

    print(f"\n--- DATOS CRUDOS ---")
    df_filt = filtrar(df)

    df_filt.to_csv(CSV_FILE, index=False)
    print(f"\nCSV guardado: {CSV_FILE} ({len(df_filt)} filas)")

    print(f"\n--- ENTRENAMIENTO ---")
    dt = entrenar(df_filt)

    code = exportar_c(dt)
    with open(MODEL_H, "w") as f:
        f.write(code)
    print(f"\nModelo exportado: {MODEL_H}")

    print(f"\n--- ESTADISTICAS ---")
    stats = df_filt.groupby("label")[FEAT].describe()
    print(stats.round(2).to_string())

if __name__ == "__main__":
    main()
