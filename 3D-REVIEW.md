# 3D: punti da rivedere

Annotazioni raccolte mentre facevo le viste 3D (mensole e scaffali, modelli da parete), le
decorazioni e l'esploso. Per ognuno: cosa ho fatto, perché è dubbio, cosa si può decidere.

## Pezzi lasciati fuori

- **SBCMicroRack**: il supporto dell'interruttore (`--switch`) non ha fori né indicazioni su dove
  vada: non compare nel 3D.
- **StackableBin**: la striscia portaetichetta opzionale non è mostrata (non si sa dove si incolla).
- **SpicesRack** con i piedi: il generatore disegna comunque anche i supporti della fila più bassa,
  che i piedi sostituiscono; quelli in più non sono mostrati.
- **StorageShelf** con coperchio `v`: le parti della cerniera non sono mostrate.
- **StorageRack** con bordo superiore `S`: il secondo ripiano pieno non ha dove agganciarsi ed è
  lasciato fuori.
- **SkadisBoard**: le 8 rondelle non hanno una posizione data.
- **RollHolder / WallRollHolder**: i due anelli dell'asse non sono un pezzo a sé nel disegno (finiscono
  dentro la piastra) e non compaiono; manca anche l'asse (tassello/tubo, non tagliato).
- **SkadisStand**: il generatore disegna un solo piede, il pannello ne vuole due: ne mostro uno.
- **WineRack** `walls=minimal`: il generatore disegna più pareti di quante ne abbiano i fori (30
  contro 22 con i valori predefiniti); quelle in più non sono mostrate.

## Incongruenze del generatore originale (ho seguito i fori)

- **PaintStorage**: alto e basso sono invertiti rispetto ai nomi; il piano "additional bottom"
  finisce in alto. La foto di esempio mette il piano coi fori più in alto di quanto risulti dal
  codice (forse altre impostazioni).
- **SBCMicroRack**: i bordi impilabili sono a rovescio rispetto a come il codice nomina alto/basso;
  ho seguito i fori e la foto (porte sopra ogni ripiano, piano vuoto in cima).
- **BinTray** con sezioni `sh` diverse tra loro: retro, fianchi e divisori interni ordinano `sh` in
  modo diverso. Ho seguito il profilo dei fianchi (`sh[0]` in alto) e messo i fori di fissaggio in
  alto; con `sh` uniforme non si nota.
- **StorageShelf**: i ripiani interni hanno le fessure con `sy` invertito: li ho girati perché
  combacino con i divisori.
- **StorageShelf** con coperchio `L` o `i`: il coperchio è disegnato ruotato rispetto alle pareti
  (lunghezze scambiate); lo mostro appoggiato sopra, orientato come il ripiano.
- **WallPliersHolder**: i rinforzi interni sono centrati dove il generatore mette i fori, mezzo
  spessore fuori dal confine tra gli scomparti.
- **DisplayShelf** con angolo negativo: i divisori, perpendicolari al ripiano inclinato,
  sporgono dal retro di qualche mm. È la geometria del generatore.

## Geometria ricavata a ragionamento: verificare nell'app

- **DinRailBox**: orientamento della clip (gancio in alto, chiavistello in basso) e posizione del
  chiavistello nell'intercapedine dietro il retro, guidato dalla striscia `feee`. Coerente coi fori,
  ma il chiavistello è il pezzo meno sicuro.
- **WallDrillBox / DrillStand**: sopra a livello, fondo che scende verso destra di `extra_height`,
  divisori verticali. Approssimazione di qualche decimo di mm sul piano del fondo.
- **WallHopper**: il sistema locale dei fianchi (`polygonWall`) è ricavato dai fori, non dal codice.
- **WallWrenchHolder**: verso delle fessure (dalla parte anteriore verso il muro, scendendo).
- **WallSlottedHolder / WallChiselHolder / RollHolder**: i triangoli di rinforzo sono disegnati
  annidati in un unico pezzo; li separo riconoscendoli dagli ingombri. Funziona con tutti i tipi di
  muro provati, ma è euristico.
- **WallEdges** è una dimostrazione dei bordi: mostro i quattro pannelli in fila, non un oggetto.
- Tipi di muro diversi da "plain": provati senza errori su tutti i modelli, controllati a vista solo
  col cleat francese (WallConsole, WallHook, WallPliersHolder, WallHopper, WallPinRow,
  WallSlottedHolder, WallTypeTray).

## Decorazioni

- **WineRack**: la spalla della bottiglia è a gradini; nel render Blender si vedono gli anelli.
  Con fori piccoli (`radius` basso) le bottiglie, rimpicciolite, stanno tutte dentro il portabottiglie.
- **DiscRack**: il diametro predefinito del generatore è 150 mm, un LP è 300 mm.
- **PaintStorage**: nessuna boccetta nel cassetto (non ha fori) né quando il generatore non disegna
  fori (fori più larghi del vassoio).
- Colori dei nuovi materiali (bottiglie, barattoli, vinili, colori) da giudicare nell'app.

## Esploso

- I pezzi incollati a strati (es. coperchio frontale e pannello del WineRack) si muovono quasi
  insieme.
- Il controllo delle compenetrazioni usa riquadri che contengono i pezzi: una parte con intagli o
  fori può essere sollevata più del necessario (mai il contrario).
- Distanze regolabili: `spread` (0.6) e `gap` (8 % della scatola) in `AssemblyStage`
  (`EditorView.swift`).

## Modifiche trasversali da tenere d'occhio

- Tolleranza di chiusura dei contorni portata da 0,2 a 0,3 mm in `loops_of` (SkadisStand e il
  chiavistello DinRailBox restano aperti di 0,22 mm). Nessun altro modello cambia con i valori
  predefiniti; con altri parametri non l'ho verificato.

## Ancora da fare

- Modelli da parete e DrillStand: compilati e avviati, da provare nell'app; commit non ancora pushati.
