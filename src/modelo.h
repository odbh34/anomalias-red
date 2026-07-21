/*
 * modelo.h – Árbol de decisión TinyML para clasificación
 * de tráfico DNS en 3 clases.
 *
 * Generado automáticamente por procesar.py a partir de
 * dataset.csv con scikit-learn DecisionTreeClassifier.
 *
 * Features (escaladas ×100 para usar int32_t):
 *   [0] dns_qty    – consultas DNS en la ventana
 *   [1] dns_unique – dominios distintos en la ventana
 *   [2] dns_new    – dominios nunca antes vistos
 *
 * Clases:
 *   0 = background (tráfico de fondo, ej. sistema)
 *   1 = foreground (navegación activa del usuario)
 *   2 = sospechoso  (picos anómalos de DNS)
 *
 * Estructura del árbol: 13 nodos, umbrales en ×100.
 * feature<0 indica nodo hoja (predicción directa).
 */

#ifndef MODELO_H
#define MODELO_H

#define N_FEATURES 3

enum feature {
    FEAT_DNS_QTY = 0,
    FEAT_DNS_UNIQUE = 1,
    FEAT_DNS_NEW = 2,
};

typedef struct {
    int16_t feature;    // Índice de feature a evaluar (-1 = hoja)
    int16_t threshold;  // Umbral (escalado ×100)
    int16_t left;       // Índice hijo si feature <= threshold
    int16_t right;      // Índice hijo si feature > threshold
    int16_t prediction; // Clase predicha (solo en hoja)
} Node;

static const Node tree[13] = {
    /*  0 */ {0, 150, 1, 4, -1},    // dns_qty <= 150? -> bg (n1) else (n4)
    /*  1 */ {2, 50, 2, 3, -1},     // dns_new <= 50?  -> bg (n2) else bg (n3)
    /*  2 */ {-1, 0, -1, -1, 0},    // -> background
    /*  3 */ {-1, 0, -1, -1, 0},    // -> background
    /*  4 */ {0, 950, 5, 12, -1},   // dns_qty <= 950? -> fg/sos (n5) else sos (n12)
    /*  5 */ {2, 50, 6, 9, -1},     // dns_new <= 50?  -> sos (n6) else fg (n9)
    /*  6 */ {0, 350, 7, 8, -1},    // dns_qty <= 350? -> sos (n7) else sos (n8)
    /*  7 */ {-1, 0, -1, -1, 2},    // -> sospechoso
    /*  8 */ {-1, 0, -1, -1, 2},    // -> sospechoso
    /*  9 */ {0, 350, 10, 11, -1},  // dns_qty <= 350? -> fg (n10) else fg (n11)
    /* 10 */ {-1, 0, -1, -1, 1},    // -> foreground
    /* 11 */ {-1, 0, -1, -1, 1},    // -> foreground
    /* 12 */ {-1, 0, -1, -1, 2},    // -> sospechoso
};

static inline int predecir(const int32_t *features) {
    int idx = 0;
    while (1) {
        if (tree[idx].feature < 0)
            return tree[idx].prediction;
        if (features[tree[idx].feature] <= tree[idx].threshold)
            idx = tree[idx].left;
        else
            idx = tree[idx].right;
    }
}

#endif /* MODELO_H */