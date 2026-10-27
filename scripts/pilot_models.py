"""Exploratory from-scratch IF and RF on chronological Kraken training data.
Liu, Ting & Zhou (2008); Breiman (2001). Not final thesis evaluation.
"""
import math, random, statistics, csv
from pathlib import Path
from pilot_detectors import read_features

ROOT=Path(__file__).resolve().parents[1]
CUTOFF='2026-10-26 15:15:00+00:00'
SEED=2008
PSI=256
TREES=100
THRESHOLD=.6

def c(n):
    if n<=1: return 0.
    if n==2: return 1.
    return 2*(math.log(n-1)+.5772156649)-2*(n-1)/n

def itree(rows, rng, depth=0, cap=8):
    if len(rows)<=1 or depth>=cap: return ('leaf',len(rows))
    candidates=[j for j in range(3) if min(x[j] for x in rows)<max(x[j] for x in rows)]
    if not candidates:return ('leaf',len(rows))
    j=rng.choice(candidates)
    lo,hi=min(x[j] for x in rows),max(x[j] for x in rows)
    v=rng.uniform(lo,hi)
    left=[x for x in rows if x[j]<v]
    right=[x for x in rows if x[j]>=v]
    if not left or not right:return ('leaf',len(rows))
    return (j,v,itree(left,rng,depth+1,cap),itree(right,rng,depth+1,cap))

def path(node,x,depth=0):
    if node[0]=='leaf':return depth+c(node[1])
    return path(node[2] if x[node[0]]<node[1] else node[3],x,depth+1)

def train_if(rows):
    rng=random.Random(SEED)
    return [itree(rng.sample(rows,PSI),rng) for _ in range(TREES)]

def anomaly_score(trees,x):
    avg=sum(path(tree,x) for tree in trees)/len(trees)
    return 2**(-avg/c(PSI))

def gini(positives,n):
    if n==0:return 0
    p=positives/n
    return 2*p*(1-p)

def rftree(rows,rng,depth=0):
    positives=sum(y for x,y in rows)
    if positives==0 or positives==len(rows):return ('leaf',int(positives>0),len(rows))
    j=rng.randrange(3) # floor(sqrt(3)) = 1 feature per split
    ordered=sorted(rows,key=lambda pair:pair[0][j])
    total=len(rows)
    left_pos=0
    best=(float('inf'),None,None)
    for k in range(1,total):
        left_pos+=ordered[k-1][1]
        if ordered[k-1][0][j]==ordered[k][0][j]:continue
        right_pos=positives-left_pos
        score=k/total*gini(left_pos,k)+(total-k)/total*gini(right_pos,total-k)
        if score<best[0]:
            best=(score,(ordered[k-1][0][j]+ordered[k][0][j])/2,k)
    if best[1] is None:return ('leaf',int(2*positives>=total),total)
    k=best[2]
    return (j,best[1],rftree(ordered[:k],rng,depth+1),rftree(ordered[k:],rng,depth+1))

def train_rf(rows,n_trees=TREES):
    rng=random.Random(2001)
    return [rftree([rows[rng.randrange(len(rows))] for _ in rows],rng)
            for _ in range(n_trees)]

def rf_predict(forest,x):
    votes=0
    for tree in forest:
        node=tree
        while node[0]!='leaf':
            node=node[2] if x[node[0]]<node[1] else node[3]
        votes+=node[1]
    return int(votes*2>=len(forest))

def main():
    historical=[z for z in read_features(ROOT/'data'/'btc_15m.csv') if z[0]<=CUTOFF]
    assert len(historical)==2850
    train_raw=historical[:1995]; val_raw=historical[1995:]
    mu=[statistics.mean(v[j] for t,v in train_raw) for j in range(3)]
    sd=[statistics.stdev(v[j] for t,v in train_raw) for j in range(3)]
    def standard(rows):
        return [(t,tuple((v[j]-mu[j])/sd[j] for j in range(3))) for t,v in rows]
    train=standard(train_raw);val=standard(val_raw)
    forest_if=train_if([v for t,v in train])
    train_scores=[anomaly_score(forest_if,v) for t,v in train]
    val_scores=[anomaly_score(forest_if,v) for t,v in val]
    labels=[int(s>=THRESHOLD) for s in train_scores]
    rf=train_rf([(v,y) for (t,v),y in zip(train,labels)])
    pred=[rf_predict(rf,v) for t,v in val]
    actual=[int(s>=THRESHOLD) for s in val_scores]
    tp=sum(y==1 and p==1 for y,p in zip(actual,pred))
    fp=sum(y==0 and p==1 for y,p in zip(actual,pred))
    fn=sum(y==1 and p==0 for y,p in zip(actual,pred))
    tn=sum(y==0 and p==0 for y,p in zip(actual,pred))
    lines=['# Uji kecil IF dan RF dari rumus paper','','Bukan hasil uji akhir.',
           f'Jumlah latih: {len(train)}, validasi: {len(val)}',
           f'IF: psi={PSI}, pohon={TREES}, batas skor={THRESHOLD}',
           f'Skor tiga baris latih awal: {train_scores[:3]}',
           f'Label anomali latih: {sum(labels)} dari {len(labels)}',
           f'Label anomali validasi: {sum(actual)} dari {len(actual)}',
           f'RF: pohon={TREES}, satu fitur acak per simpul, Gini, bootstrap',
           f'Validasi proxy label: TP={tp}, FP={fp}, FN={fn}, TN={tn}',
           f'Prediksi anomali validasi: {sum(pred)} dari {len(pred)}',
           f'Pohon IF pertama: akar={forest_if[0][0:2]}',
           f'Pohon RF pertama: akar={rf[0][0:2]}',
           'Rujukan: https://doi.org/10.1109/ICDM.2008.17 ; https://doi.org/10.1023/A:1010933404324',
           'Ambang skor 0,6 adalah contoh calon anomali pada Liu et al.; perlu cek sensitivitas.']
    out=ROOT/'reports'/'pilot_models.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(out)
if __name__=='__main__':main()

