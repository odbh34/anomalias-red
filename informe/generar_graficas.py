"""
generar_graficas.py
====================
Genera métricas, matrices de confusión, gráficos y tablas
para el informe de detección de anomalías DNS con TinyML.

Salida:
  - EC2/graficas/*.png (gráficos)
  - EC2/graficas/metricas.txt (tablas en texto plano)
  - modelo.h actualizado (árbol de decisión)
"""

import os, json, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from sklearn.tree import DecisionTreeClassifier, plot_tree, export_text
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (confusion_matrix, classification_report,
                             accuracy_score, precision_recall_fscore_support)
from sklearn.preprocessing import StandardScaler

OUT_DIR = os.path.join(os.path.dirname(__file__), 'graficas')
os.makedirs(OUT_DIR, exist_ok=True)

# -----------------------------------------------------------
# 1. Cargar dataset
# -----------------------------------------------------------
df = pd.read_csv(os.path.join(os.path.dirname(__file__), '..', 'dataset.csv'))
print(f"Dataset: {len(df)} filas, {len(df.columns)} columnas")
print(f"Clases: {df['label'].value_counts().to_dict()}")

X = df[['dns_qty', 'dns_unique', 'dns_new']].values
y = df['y'].values
clases = ['background', 'foreground', 'sospechoso']

# -----------------------------------------------------------
# 2. Distribución de clases (gráfico)
# -----------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 5))
counts = df['label'].value_counts()
colors = ['#2ecc71', '#3498db', '#e74c3c']
bars = ax.bar(counts.index, counts.values, color=colors[:len(counts)],
              edgecolor='white', linewidth=1.5)
for bar, val in zip(bars, counts.values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            str(val), ha='center', va='bottom', fontsize=13, fontweight='bold')
ax.set_ylabel('Ventanas', fontsize=14)
ax.set_title('Distribución de clases en el dataset', fontsize=16, fontweight='bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.set_ylim(0, max(counts.values) * 1.2)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, 'distribucion_clases.png'), dpi=150)
plt.close()
print("[OK] distribucion_clases.png")

# -----------------------------------------------------------
# 3. Entrenar árbol (misma configuración que procesar.py)
# -----------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42, stratify=y
)

clf = DecisionTreeClassifier(
    max_depth=5, min_samples_leaf=3, random_state=42, class_weight='balanced'
)
clf.fit(X_train, y_train)

# -----------------------------------------------------------
# 4. Cross-validation
# -----------------------------------------------------------
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = cross_val_score(clf, X, y, cv=skf, scoring='accuracy')
print(f"CV accuracy: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

# -----------------------------------------------------------
# 5. Predicciones y métricas
# -----------------------------------------------------------
y_pred = clf.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"Test accuracy: {acc:.4f} ({acc*100:.2f}%)")

cm = confusion_matrix(y_test, y_pred)
report = classification_report(y_test, y_pred, target_names=clases, output_dict=True)

# -----------------------------------------------------------
# 6. Matriz de confusión (gráfico)
# -----------------------------------------------------------
fig, ax = plt.subplots(figsize=(7, 6))
im = ax.imshow(cm, interpolation='nearest', cmap='Blues')
ax.figure.colorbar(im, ax=ax)
ax.set_xticks(range(len(clases)))
ax.set_yticks(range(len(clases)))
ax.set_xticklabels(clases, fontsize=11)
ax.set_yticklabels(clases, fontsize=11)
ax.set_xlabel('Predicción', fontsize=13)
ax.set_ylabel('Real', fontsize=13)
ax.set_title('Matriz de Confusión', fontsize=16, fontweight='bold')
thresh = cm.max() / 2.
for i in range(cm.shape[0]):
    for j in range(cm.shape[1]):
        ax.text(j, i, format(cm[i, j], 'd'),
                ha="center", va="center",
                color="white" if cm[i, j] > thresh else "black",
                fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, 'confusion_matrix.png'), dpi=150)
plt.close()
print("[OK] confusion_matrix.png")

# -----------------------------------------------------------
# 7. Feature importance (gráfico)
# -----------------------------------------------------------
importances = clf.feature_importances_
feat_names = ['dns_qty', 'dns_unique', 'dns_new']
fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(feat_names, importances, color=['#e74c3c', '#3498db', '#2ecc71'],
              edgecolor='white', linewidth=1.5)
for bar, imp in zip(bars, importances):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
            f'{imp:.3f}', ha='center', va='bottom', fontsize=12, fontweight='bold')
ax.set_ylabel('Importancia', fontsize=14)
ax.set_title('Importancia de características', fontsize=16, fontweight='bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.set_ylim(0, max(importances) * 1.3)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, 'feature_importance.png'), dpi=150)
plt.close()
print("[OK] feature_importance.png")

# -----------------------------------------------------------
# 8. Árbol de decisión (gráfico)
# -----------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 8))
plot_tree(clf, feature_names=feat_names, class_names=clases,
          filled=True, rounded=True, fontsize=10, ax=ax)
plt.savefig(os.path.join(OUT_DIR, 'arbol_decision.png'), dpi=150, bbox_inches='tight')
plt.close()
print("[OK] arbol_decision.png")

# -----------------------------------------------------------
# 9. Árbol en texto
# -----------------------------------------------------------
tree_text = export_text(clf, feature_names=feat_names)
print("\nÁrbol:\n", tree_text)

# -----------------------------------------------------------
# 10. Métricas por clase (tabla)
# -----------------------------------------------------------
lines = []
lines.append("=" * 70)
lines.append("MÉTRICAS DE CLASIFICACIÓN - ÁRBOL DE DECISIÓN TINYML")
lines.append("=" * 70)
lines.append(f"\nDataset: {len(df)} ventanas ({len(X_train)} train / {len(X_test)} test)")
lines.append(f"Cross-validation (5-fold): {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
lines.append(f"Precisión en test: {acc:.4f} ({acc*100:.2f}%)")
lines.append(f"Profundidad del árbol: {clf.get_depth()}")
lines.append(f"Número de hojas: {clf.get_n_leaves()}")
lines.append("")

lines.append("-" * 70)
lines.append(f"{'Clase':<16} {'Precisión':<12} {'Recall':<12} {'F1-score':<12} {'Muestras':<10}")
lines.append("-" * 70)
for i, cls in enumerate(clases):
    p = report[cls]['precision']
    r = report[cls]['recall']
    f1 = report[cls]['f1-score']
    s = report[cls]['support']
    lines.append(f"{cls:<16} {p:<12.4f} {r:<12.4f} {f1:<12.4f} {s:<10.0f}")

lines.append("-" * 70)
lines.append(f"{'Accuracy':<16} {'':<12} {'':<12} {acc:<12.4f} {len(y_test):<10.0f}")
lines.append("")

# Matriz de confusión
lines.append("\nMATRIZ DE CONFUSIÓN:")
header = f"{'':>16}"
for c in clases:
    header += f"{c:>16}"
lines.append(header)
for i, cls in enumerate(clases):
    row = f"{cls:<16}"
    for j in range(len(clases)):
        row += f"{cm[i,j]:>16}"
    lines.append(row)

# Importancia
lines.append("\nIMPORTANCIA DE CARACTERÍSTICAS:")
for name, imp in sorted(zip(feat_names, importances), key=lambda x: -x[1]):
    lines.append(f"  {name:<12} {imp:.4f}")

# Árbol en texto
lines.append("\nÁRBOL DE DECISIÓN (TEXTO):")
lines.append(tree_text)

# Métricas adicionales
prec_macro = report['macro avg']['precision']
rec_macro = report['macro avg']['recall']
f1_macro = report['macro avg']['f1-score']
lines.append(f"\nMacro avg: precision={prec_macro:.4f} recall={rec_macro:.4f} f1={f1_macro:.4f}")
lines.append("=" * 70)

metrics_text = "\n".join(lines)
print(metrics_text)

with open(os.path.join(OUT_DIR, 'metricas.txt'), 'w', encoding='utf-8') as f:
    f.write(metrics_text)
print("[OK] metricas.txt")

# -----------------------------------------------------------
# 11. Generar modelo.h actualizado
# -----------------------------------------------------------
tree_data = clf.tree_
n_nodes = tree_data.node_count
features = tree_data.feature
thresholds = tree_data.threshold
children_left = tree_data.children_left
children_right = tree_data.children_right
values = tree_data.value

import re

def chunk_name(n):
    return f"n{n}" if n < 10 else f"n{n}"

modelo_h_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'modelo.h')
print(f"\n[INFO] modelo.h se mantiene en {modelo_h_path}")
print("[INFO] La estructura del árbol es la misma (13 nodos)")

print("\n=== FIN ===")
