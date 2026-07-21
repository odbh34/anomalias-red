#ifndef MODELO_H
#define MODELO_H

/* Generado por procesar.py -- Arbol TinyML */
/* Features: dns_qty, dns_unique, dns_new */
/* Clases: 0=background, 1=foreground, 2=sospechoso */

#define N_FEATURES 3

enum feature {
    FEAT_DNS_QTY = 0,
    FEAT_DNS_UNIQUE = 1,
    FEAT_DNS_NEW = 2,
};

typedef struct {
    int16_t feature;
    int16_t threshold;
    int16_t left;
    int16_t right;
    int16_t prediction;
} Node;

static const Node tree[13] = {
    {0, 150, 1, 4, -1},
    {2, 50, 2, 3, -1},
    {-1, 0, -1, -1, 0},
    {-1, 0, -1, -1, 0},
    {0, 950, 5, 12, -1},
    {2, 50, 6, 9, -1},
    {0, 350, 7, 8, -1},
    {-1, 0, -1, -1, 2},
    {-1, 0, -1, -1, 2},
    {0, 350, 10, 11, -1},
    {-1, 0, -1, -1, 1},
    {-1, 0, -1, -1, 1},
    {-1, 0, -1, -1, 2},
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