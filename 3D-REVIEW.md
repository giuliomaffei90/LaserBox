# 3D: punti da rivedere

Annotazioni raccolte mentre facevo le viste 3D (mensole e scaffali, modelli da parete, motivi di fori,
pezzi di test, pezzi e campioni), le decorazioni e l'esploso. Per ognuno: cosa ho fatto, perché è dubbio, cosa si può decidere.

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
- **RollHolder / WallRollHolder**: i due anelli dell'asse ora arrivano al 3D (erano l'ultimo tracciato
  del disegno, che andava perso) ma non sono ancora posizionati: non compaiono. L'asse c'è come
  decorazione.
- **FrontPanel**: i fori fuori da ogni `outline` non sono mostrati; senza `outline` il 3D è vuoto.
- **Gears**: la dima coi due fori all'interasse (e il testo con le misure) non ha contorno: non c'è.
- **NemaMount**: i fori per le dita disegnati per ultimi, da tagliare in una piastra propria su cui
  fissare la staffa, non sono mostrati.
- **Linkage**: è un kit; monto solo un quadrilatero articolato sulla base (manovella = asta l/4,
  biella = 3/4 l, bilanciere = l/2, tra i fori estremi della fila centrale, posizione scelta da me),
  con un distanziale sotto manovella e bilanciere. Gli altri 8 dischi e 14 aste non compaiono.
- **RobotArm**: solo i tubi dei segmenti, in fila a 15 mm l'uno dall'altro: niente servo e niente
  collegamento tra un segmento e l'altro.
- **Planetary** con `deltateeth`: la seconda corona e i suoi satelliti stanno nello strato sopra,
  sulle stesse posizioni, senza calcolarne l'ingranamento.
- **Pulley**: il generatore disegna un solo bordo (`top`), che metto sopra; sotto non c'è.
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
- **SevenSegmentPattern**: il secondo separatore è disegnato 0,8 mm più corto dei suoi fori; l'ho
  centrato sui fori.
- **FanHole**: i bracci della girandola restano aperti di 0,34 mm (diametro 80): li chiudo come fori.
  Con diametri piccoli (40 mm, 10 bracci) i bracci del generatore si incrociano e alcuni fori si
  fondono.
- **RobotArm**: con i valori predefiniti il generatore non disegna nulla. Ho messo come predefiniti
  dell'app due segmenti (Mm e Mu): cambia anche il disegno 2D.
- **ZBeam**: z ha la stessa descrizione di y ("profondità interna"); è la seconda ala della Z.
- **StackableBin / WallStackableBin**: le misure dipendono dalla distanza tra i pezzi; col nuovo
  default di 2 mm l'altezza cala di 0,5 mm e la profondità cresce di 0,2. Il 3D segue il disegno.
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

- **Motivi di fori**: i generatori disegnano solo i fori, nessun pannello. Il pannello l'ho scelto io:
  FanHole e NemaPattern quadrato, 10 mm più largo di ventola/motore; HolePattern della forma del
  bordo che i fori riempiono (senza margine oltre `space_to_border`); FrontPanel i rettangoli degli
  `outline`, affiancati a 10 mm come nel disegno; SevenSegmentPattern due piastre grandi quanto il
  contorno dei separatori più uno spessore. Tutti in piedi, letti di fronte.
- **SevenSegmentPattern**: piastra coi segmenti davanti, separatori infilati nelle fessure della
  piastra dietro (la foto li mostra smontati). Posizioni dei separatori ricavate ripercorrendo
  `seven_segment_holes`, coppia per coppia nell'ordine in cui sono disegnati.
- **BurnTest**: ogni coppia montata ad angolo come nella foto: il pezzo con le tacche (F) a terra,
  quello con le dita (f) in piedi sul suo bordo posteriore. Si vede un solo incastro per coppia; i
  pezzi sono riconosciuti da dove il generatore li inizia, perché non ne fa parti separate.
- **FlexTest / FlexTest2**: piegati di un quarto di giro, col raggio per cui la parte flessibile copre
  l'arco. FlexTest2 flette in due direzioni: piegarlo su un asse solo è una scelta (una cupola sarebbe
  più fedele). FillTest è piatto.

- **ConcaveKnob / WavyKnob**: i tre dischi impilati sottosopra (quello liscio a terra, quello col
  foro esagonale per la testa del bullone, quello col foro a D sopra), il bullone verso l'alto.
- **LaserHoldfast**: in piedi sulla punta del gambo, il gancio in alto; nessun piano a nido d'ape.
- **NemaMount**: appoggiata sulla piastra con le asole, la piastra del motore davanti e il motore
  dentro, l'albero in avanti. La foto la mostra con la piastra del motore a terra.
- **GearBox**: strati di ruote ricavati dal codice: in ognuno una ruota piccola su un albero muove
  una grande sull'altro, alternandosi; ogni grande è incollata alla piccola dello strato dopo.
- **Gears / GearBox / Planetary**: la fase dei denti è calcolata perché ingranino (la
  sovrapposizione che resta è quella del kerf). Il portasatelliti copre quasi tutto il planetario.
- **RectangularWall / TriangularWall**: in piedi, viste di fronte.

## Decorazioni

- **WineRack**: la spalla della bottiglia è a gradini; nel render Blender si vedono gli anelli.
  Con fori piccoli (`radius` basso) le bottiglie, rimpicciolite, stanno tutte dentro il portabottiglie.
- **DiscRack**: il diametro predefinito del generatore è 150 mm, un LP è 300 mm.
- **PaintStorage**: nessuna boccetta nel cassetto (non ha fori) né quando il generatore non disegna
  fori (fori più larghi del vassoio).
- **FanHole**: ventola nera stilizzata dietro il pannello (telaio coi fori, mozzo, 7 pale piatte),
  profonda 0,3 volte il diametro, al massimo 25 mm.
- **NemaPattern**: motore passo-passo lungo quanto largo (le lunghezze reali variano), calotte nere,
  pacco in acciaio, centraggio nel foro grande, albero che esce davanti.
- Senza contenuto: FrontPanel (pulsanti, il motore NEMA del terzo pannello), HolePattern,
  SevenSegmentPattern (la striscia LED), i pezzi di test.
- **Pezzi e campioni**: bullone delle manopole, alberi della GearBox, perni del planetario e del
  quadrilatero, asse della puleggia, motore della NemaMount (lungo quanto largo, come in NemaPattern).
- Colori dei nuovi materiali (bottiglie, barattoli, vinili, colori) da giudicare nell'app.

## Esploso

- I pezzi incollati a strati (es. coperchio frontale e pannello del WineRack) si muovono quasi
  insieme.
- Il controllo delle compenetrazioni usa riquadri che contengono i pezzi: una parte con intagli o
  fori può essere sollevata più del necessario (mai il contrario).
- Distanze regolabili: `spread` (0.6) e `gap` (8 % della scatola) in `AssemblyStage`
  (`EditorView.swift`).

## Modifiche trasversali da tenere d'occhio

- `assemble` ora chiude l'ultimo tracciato lasciato aperto dal generatore (come fa `close()`): senza,
  la girandola di FanHole spariva. Tra i modelli già fatti cambiava solo RollHolder (gli anelli, ora
  esclusi apposta); gli altri restano identici con i valori predefiniti.
- `Placement(plate=…)`: per i pezzi fatti di soli fori, i fori che stanno dentro la lastra vengono
  sottratti dalla lastra.

- Tolleranza di chiusura dei contorni portata da 0,2 a 0,3 mm in `loops_of` (SkadisStand e il
  chiavistello DinRailBox restano aperti di 0,22 mm). Nessun altro modello cambia con i valori
  predefiniti; con altri parametri non l'ho verificato.

## Pannello Skadis e oggetti appesi

- Il pannello forato (bianco, 5 mm, asole Skadis) sta dietro ogni oggetto da parete, 40 mm più largo
  tutto intorno. Anche SpicesRack e BinTray (gruppo Mensole, ma appesi al muro). Non su SkadisBoard
  (è il pannello) né su WallEdges (dimostrazione). Lo SkadisStand ha il pannello appoggiato sui ganci;
  il DinRailBox ha anche la barra DIN.
- Con muro "skadis" i ganci entrano nel pannello ma non sono allineati alle sue asole (le larghezze
  dei modelli non seguono il passo di 40 mm); con "french cleat", "slatwall" e "dinrail" il pannello
  c'è lo stesso, anche se nella realtà il sistema di fissaggio sarebbe un altro: da decidere se
  mostrare il sistema giusto per ogni tipo di muro.
- Il pannello compare anche nelle card della galleria (rimpicciolisce l'oggetto) e nell'esploso
  svanisce con le altre decorazioni.
- Oggetti appesi aggiunti: rotolo da cucina con asse, pialla, calibro, chiavi inglesi, scalpelli,
  cacciaviti, pinze, chiavi, punte da trapano (anche in DrillStand), barattoli di spezie su WallRack.
- Senza contenuto, perché generici: WallHook, WallPinRow, WallConsole, WallTypeTray,
  WallStackableBin, WallHopper, WallStairs. Si potrebbero riempire (borse, cuffie, viti…).
- La pialla sta quasi tutta dentro il porta-pialla e si vede poco.
- Le posizioni di fessure e fori (chiavi inglesi, scalpelli) vengono dal contorno del generatore
  ripercorso a mano: se il generatore cambia il disegno, vanno riviste.

## Ancora da fare

- Modelli da parete e DrillStand: compilati, avviati e pushati; da provare nell'app.
- Motivi di fori e pezzi di test (nuova categoria "Test", ultima): compilati e avviati; da provare nell'app.
- Pezzi e campioni: non compilati; da provare nell'app.
