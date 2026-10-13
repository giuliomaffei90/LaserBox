# 3D: punti da rivedere

Annotazioni raccolte mentre facevo le viste 3D (mensole e scaffali, modelli da parete, motivi di fori,
pezzi di test, pezzi e campioni, "Varie"), le decorazioni e l'esploso. Per ognuno: cosa ho fatto, perché è dubbio, cosa si può decidere.

## Pezzi lasciati fuori

- **SBCMicroRack**: il supporto per lo switch di rete (`--switch`) è un terzo fianco senza fori
  per i ripiani: ha solo il foro per il tondino (con `--stable`), che c'è anche nel fianco senza
  porte. Forse sta parallelo a quel fianco, con lo switch in mezzo, ma la distanza non è data:
  non compare nel 3D.
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
- **Arcade**: `side()` disegna prima, in un `saved_context`, il contorno a spigoli vivi (r = 10 dentro quello vero arrotondato): tagliato davvero dividerebbe ogni fianco in una cornice larga 10 mm e un pannello interno con tutti i fori. Nel 3D quel tracciato (il primo path del pezzo) è tolto e il fianco è un pezzo unico; sembra un residuo del generatore, da verificare sul file tagliato.
- **OttoBody**: i due PCB_Clamp, il PCB_Clip e la piastrina 15×15 del pulsante sono lasciati fuori: non hanno incastri né fori corrispondenti nel corpo, quindi non si sa dove vanno (probabilmente tengono l'Arduino nella testa).
- **PhotoFrame**: la "Photo" che il generatore disegna è solo una sagoma (niente da tagliare): non è piazzata come parte, la foto è mostrata come decorazione di carta. Il vetro non è mostrato (non è tagliato e non c'è un tipo di decorazione per il vetro).
- **CanStorage**: il pezzo "invisible" è solo uno spostamento ("left only"), non viene disegnato: niente da piazzare.
- **CarbonFilter**: manca il bordo superiore di listelli di legno (2–3 cm) che la descrizione del generatore chiede di incollare intorno: non è tagliato, non l'ho aggiunto. Mancano anche la rete e il carbone tra i due binari di ogni falda.
- **AgricolaInsert**: il separatore di carta del vassoio delle carte (generate_paper_divider) non è montato: è di carta e sta libero fra le carte; senza carte resterebbe in piedi appoggiato a niente, e in 3D sarebbe spesso come il legno.
- **AgricolaInsert**: niente carte, tessere, segnalini né i due cartoncini che la descrizione mette fra le scatole basse e i vassoi superiori.
- **PoleHook**: la vite centrale (bedBolt nei forchettoni, testa nei dischi esagonali della manopola) non è disegnata: resta nascosta dentro la pila.
- **Kamishibai**: con "three-part lid, hinges not provided" il generatore non disegna nessuna copertura frontale (né pannelli né serrature): `render()` confronta lo stile con "three-part lid, higes not provided" (refuso), quindi non c'è niente da piazzare; la scatola resta aperta davanti.
- **FatBallDispenser**: gancio, rondella, dadi e rete metallica non sono modellati (non sono pezzi tagliati); solo pali e palline come decorazioni.
- **Shadowbox**: gli strati di carta tagliata fra un telaio e l'altro (l'arte dell'utente) non ci sono; c'è solo lo strato bianco di fondo come decorazione.
- **LaserClamp**: la molla / gli elastici che tengono chiusa la pinza non ci sono (il generatore non dice dove agganciarli: nella foto passano nel foro della testa tonda e nella tacca sotto la parte inferiore).
- **SevenSegmentClock**: niente striscia LED né diffusore (la descrizione suggerisce carta sopra o sotto i fori): dietro i segmenti si vedono solo i separatori di legno.
- **Stachel**: le viti (o i bulloni) che stringono i due morsetti a fessura (quello sull'anello e quello sul palo), e i blocchetti di legno che si vedono nella foto, non sono disegnati dal generatore: lasciati fuori. Le asole da 2 mm dello strato centrale restano vuote.
- **Stachel**: non c'è il flauto nell'anello; avevo provato un tratto del piede del flauto ma copriva tutto il pezzo, così è rimasto solo il palo.
- **PaperBox**: i segni di piegatura (le piccole tacche sul contorno) e le sbavature del burn lungo le pieghe sono tolti (ogni pannello è "aperto" di 0,2 mm); i tagli di bloccaggio del coperchio della tuckbox non hanno un trattamento particolare, restano come intaccature sulla piega.
- **Sphere**: le linguette (tabs) lungo i bordi degli spicchi sono tagliate via nella vista 3D (lo spicchio è ritagliato sulla sua lente, |x| ≤ halfBellyLens·sin(u/R)): nella realtà si piegano sotto lo spicchio vicino, ma piegarle non si può con le Placement; lasciate piatte sporgerebbero come pinne fuori dalla sfera.
- **Desksign**: il testo inciso sulla targa non compare (è un'incisione, non un taglio).
- **FrameLoom**: nel telaio va solo il liccio standard; i licci a disegno (2×2 e a rombo, opzionali) non sono montati: stanno distesi accanto al telaio con pettine, aghi e navette. I licci a disegno sono fatti di due pezzi incollati a croce (le linguette del liccio "clipons" nelle asole dell'altro), qui restano piatti come tagliati; dei due "clipons" si vedono le due metà separate dai tagli a zigzag, i listelli tra gli zigzag (sfrido) sono tolti. Senza il liccio standard nel telaio va il primo liccio a disegno (quello con le maniglie), senza il suo compagno a croce.
- **FrameLoom**: senza telaio (`includeframe` spento) non ci sono piedi né telaio: tutti i pezzi, liccio compreso, sono distesi in fila.
- **AllEdges**: la descrizione incisa sotto ogni campione (testo) non è un taglio e non compare.

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
- **StorageShelf** con un coperchio (`v`, `L`, `i`, `k`, `c`, `E`): ho girato il coperchio nella
  generazione (`scripts/bundle-runtime.sh` passa `y, x` a `drawLid`) perché si unisse al retro; da
  verificare su un pezzo tagliato.
- **StorageShelf** con coperchio `v`: l'asse della cerniera è ricavato dalle tacche (uno spessore sopra
  il retro, sulla sua faccia esterna). Le cerniere in stile `outside` non sono montate. Se lo scaffale
  è più stretto di una cerniera il generatore non disegna né le cerniere né il bordo del retro e del
  coperchio (pezzi rotti).
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
- **DisplayShelf** con angolo negativo: i divisori, perpendicolari al ripiano inclinato,
  sporgono dal retro di qualche mm. È la geometria del generatore.
- **Arcade**: il fondo è lungo `y − 40 − t/2` e finisce circa 28 mm prima della striscia posteriore bassa: il suo bordo a dita `f` sul retro non incastra in niente, e il bordo `F` della striscia resta libero. Ho seguito i fori dei fianchi.
- **Arcade**: la striscia posteriore alta finisce a circa h − 30, mentre il tetto inclinato ("topback") comincia sopra lo spigolo del retro: tra i due resta una fessura di circa 37 mm, visibile da dietro.
- **Arcade**: i fori della striscia posteriore bassa partono a 11,5 mm dal fondo del fianco, il fondo è a 10–13: i denti `F` della striscia scendono 1,5 mm sotto il fondo.
- **Arcade**: per il frontale, il pannello degli altoparlanti e il tetto inclinato i fori corrono nel verso opposto ai loro bordi a dita: li ho girati da capo a piedi perché il loro `f` incontri l'`F` del vicino (frontale con `f` alla tastiera, altoparlanti e tetto con `f` contro il frontale della marquee). Così gli altoparlanti stanno a 50 mm dal frontale della marquee, come nella foto.
- **Arcade**: tra il tetto inclinato (bordo `e`) e il frontale della marquee (bordo `F`) non c'è un vero incastro: i fori li mettono ad angolo, seguito così.
- **BirdHouse**: i due tetti hanno al colmo uno "f" e uno "F", ma roof() non sposta il bordo F della sua startWidth: il pannello F ha i fori a t sotto il suo bordo di colmo e le sue dita sporgono di altri t oltre il primo pannello. Ho messo ogni pannello con i fori sulle dita del timpano (il pannello F copre lo spessore dell'altro e le sue dita escono di t sopra il colmo).
- **BirdHouse**: per lo stesso motivo la gronda dei due pannelli sporge in modo diverso (overhang + 2t contro overhang + t oltre il timpano). Lasciato così.
- **BirdHouse**: render() cambia edge_width dei bordi "h" dopo aver disegnato le pareti, solo per i tetti che non hanno bordi "h": non ha effetto, ignorato.
- **OttoBody**: i fianchi sono disegnati lunghi x e il fronte/retro lunghi y, al contrario dei nomi di IntegratedHingeBox; dato che x = y = 60 (fissi nel generatore) non cambia nulla.
- **OttoBody**: il foro da 2 mm del supporto servo destro (per l'interruttore) cade per metà fuori dal pezzo (il pezzo è lungo y - 5.6, il foro è a y - 5): il dischetto staccato è scartato.
- **CanStorage**: con top_edge "e" il FrontEdge comincia con un salto (moveTo), quindi il contorno dei fianchi resta aperto (due tagli aperti) e il pezzo sparirebbe. Ho chiuso il contorno a mano: il bordo superiore tagliato dove comincia il fronte, poi il fronte (passato come `plate=`). Verificare che la forma sia quella attesa.
- **CarbonFilter**: le costole esterne (outerRibs) hanno il contorno non chiuso per uno scarto di 0,3–1,2 mm che cresce con l'angolo a (con x=550, h=250, 3 tasche si chiude, con 2 tasche o x diversi no), e la riga di costole deriva leggermente. Le ho chiuse io (Polygon + buffer(0)) e passate come `plate=` con `keep` che scarta tutto: funziona, ma così `piece_roles` le salta (niente ruolo per le etichette).
- **CarbonFilter**: `Runtime/samples/CarbonFilter.png` mostra una scatola con un coperchio a fori tondi, che non c'entra con questo filtro: l'illustrazione di esempio sembra sbagliata.
- **AgricolaInsert**: il distanziale basso del vassoio delle carte sta a 0,15 mm dalla parete a pettine (i fori sono a spacer_spacing − t/2 con spacer_spacing = larghezza − 99,8 = 3,15): l'ho messo lì, quasi a contatto.
- **AgricolaInsert**: la parete inclinata del vassoio delle carte non tocca il piano (il centro dei fori parte a sin·t/2): il piede resta sollevato di circa mezzo millimetro, come dice anche il commento del generatore.
- **AgricolaInsert**: dei piedini triangolari dei separatori mobili il generatore chiude solo il primo triangolo (il secondo condivide l'ipotenusa e resta un taglio aperto): ho usato lo stesso triangolo due volte, uno per lato.
- **AgricolaInsert**: con spessore diverso da 3 mm il vassoio delle carte del generatore si rompe (a 4 mm spacer_spacing diventa negativo): la ricetta non va in errore ma mostra quello che il generatore disegna.
- **OttoLegs**: il foro da 3 mm del pannello frontale è a cavallo dell'intaglio semicircolare: la parte del cerchio fuori dall'intaglio diventava un pezzetto staccato, che ho tolto; in 3D quel foro resta quindi solo in parte.
- **Hook**: il pannello posteriore ha bordi E (sporgenti): scende 3 mm sotto i fianchi. Seguito il disegno.
- **Kamishibai**: le due strisce 16t × t "feee" per le serrature extra (in alto e in basso) vengono sempre disegnate, ma i fori per le dita che le ricevono nei piani superiore/inferiore esistono solo con LockScrewDiameter > 0 (il blocco è indentato dentro quello delle viti). Le ho messe dove sarebbero i fori (Y = -FrontExtraDepth·t, X da wi/2 - 8t, lunghe 16t).
- **NightLightBox**: con "extra customizable face" la parete frontale e la faccia hanno tre fori quadrati ma i pioli disegnati sono due; il terzo foro ha la x calcolata da PlateVisibleHeight (PVH + 6.5t + M), probabilmente un errore. Ho messo i due pioli nei primi due fori.
- **NightLightBox**: le tavole decorative e il diffusore sono pensati spessi WoodPlateThickness / DiffuserPlateThickness (5 mm), ma in 3D tutto è estruso con lo spessore della scatola: li ho centrati nelle loro fessure.
- **FatBallDispenser**: con roof_hole_diameter = 0 il generatore va in errore (divisione per zero in `roof_tile`), quindi quell'opzione non si può provare; la ricetta gestisce comunque l'assenza del supporto.
- **FatBallDispenser**: il poligono inciso sul supporto del tetto usa `t / atan(angolo)` invece di `tan`; ho posizionato il supporto con la geometria corretta (il bordo della faccia inferiore sulle facce interne delle tegole), non con l'incisione.
- **TriangleLamp**: con sharpcorners le pareti dei cateti, allungate dal bordo C, scendono di circa 2 mm sotto il piano d'appoggio (è la parte da smussare a 22,5°); non ho modellato lo smusso.
- **Clock**: la gamba posteriore, con le tacche centrate sui due ripiani, finisce circa 1,7 mm sopra il pavimento (le gambe anteriori invece poggiano): la lunghezza oltre la tacca inferiore (2·Tf − t + Rm·(1 − cos Af) + t) non coincide con l'altezza delle spalle delle gambe anteriori. Ho seguito gli incastri e lasciato la gamba sollevata.
- **Clock**: le tacche della gamba posteriore sono larghe t − burn ma i ripiani sono spessi t: incastro forzato, mostrato centrato.
- **PizzaShovel**: `gripCB(top=True)` va alla traversa da 40, che però i fori dei fianchi mettono in basso, accanto alla pala; quella da 80 (top=False) va in alto. Ho seguito i fori (come nella foto).
- **MagazineFile**: i due fianchi sono disegnati nello stesso pezzo, il secondo dopo un `moveTo(y + 15, h + hi + 15, 180)` (girato di mezzo giro). Li ho separati ricostruendo quella trasformazione: se il generatore cambia l'ordine o gli spostamenti, il secondo fianco va fuori posto.
- **AirPurifier**: la parete che il generatore chiama "top" è alta d, ma lo spazio tra i due telai interni (o, con un filtro, tra il telaio e la piastra di chiusura) è d + 2: l'ho messa 1 mm sopra il telaio inferiore (due filtri) o contro la piastra di chiusura (un filtro).
- **AirPurifier**: con un solo filtro i fori dei ventilatori della parete "top" sono centrati a (d + t + fh)/2 su una parete alta d, quindi escono dal suo bordo: lì non metto ventilatori nella decorazione.
- **Ramp**: gli help di y e h sono scambiati rispetto al risultato: la profondità della rampa viene da y (tx ≈ y) e l'altezza da h (ty = tx·h/y); la pendenza è atan(h/y). Ho seguito i pezzi.
- **Ramp**: tra la cima della parete verticale e la diagonale resta un piccolo cuneo vuoto (la diagonale arriva al filo esterno della parete verticale, t/cos a oltre lo spigolo interno); al piede la diagonale scende fino a terra davanti al fondo. Come da generatore.
- **CoinBankSafe**: il foro della cerniera del coperchio è disegnato dal secondo callback, cioè all'inizio del bordo destro (vicino a u = y), mentre quello del fondo è vicino a u = 0: ho girato il coperchio sottosopra perché i due fori stiano uno sopra l'altro.
- **CoinBankSafe**: la maniglia è una pinna piena (1,5t × 8t con la linguetta nella fessura dello sportello), senza foro per le dita: così la disegna il generatore.
- **Sphere**: con top_hole_radius piccolo (es. 10 con raggio 100 e 8 spicchi) il generatore dà errore "cable hook radius is too big" anche con cable_hook = 0: il controllo non guarda se i ganci ci sono. Non è un problema della ricetta.
- **TrafficLight**: le tre "horizontal Wall" (schermi sopra le luci) sono uguali tranne l'ultima, col bordo posteriore di tipo back_edge: l'ho messa in cima (sopra la prima luce, dove i fianchi hanno il bordo F), le altre nei fori tra le luci; la "bottom wall" sotto, profonda solo d (senza schermo).
- **AllEdges**: il generatore disegna ogni campione solo su tre lati (su, il bordo in cima, giù) e lo lascia aperto in basso; alcuni bordi (cerniere da mobile, fori a pera "G") hanno fori sotto la linea di base, cioè fuori dalla striscia. Ho chiuso ogni campione con un fondo dritto 3t sotto il punto più basso disegnato, così i fori ci stanno; nella foto i campioni hanno il fondo ondulato e sono più alti.
- **AllEdges**: il bordo a cremagliera ("R") apre un pezzo annidato a metà disegno: il contorno prosegue in un pezzo a parte; i due tratti sono ricongiunti per estremi coincidenti.
- **AllEdges**: dove il contorno si incrocia in un angolo bruciato restano dei buchi di pochi µm che facevano sparire mezzo campione nella triangolazione (sembrava un cuneo): li tolgo (area < 0,5 mm²), come le schegge chiuse dentro.
- **DiceTower**: con `ramps` = 1 il generatore stesso va in errore (divisione per zero in `side()`); la ricetta non può farci niente.

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
- **Arcade**: il pannello posteriore grande (`backwall`, nessun incastro, alto h − 40) non ha fori che lo collochino: l'ho messo fuori dalle due strisce posteriori, dal piede di quella bassa in su (come uno sportello avvitato).
- **Arcade**: le posizioni di tutti i pannelli sono ricalcolate ripercorrendo i `polyline`/`fingerHolesAt` di `side()` (curve di raggio 10 comprese, `burn` ignorato): se il generatore cambia, il percorso in `_arcade_side` va aggiornato.
- **FilamentSpool**: montaggio della chiusura a baionetta dedotto dalla descrizione ("le parti interne vanno sul fianco, le esterne dentro l'asse") e dalla BayonetBox: poligono (strato superiore) sopra le doghe, anello esterno dello strato inferiore incollato sotto di esso dentro l'asse; anello interno liscio dello strato superiore e anello interno con le alette sull'altra flangia, nel foro del poligono e sotto. Le alette sono mostrate nella posizione in cui sono tagliate (non ruotate in chiusura).
- **FilamentSpool**: il poligono è disegnato con il primo lato in basso, i fori delle doghe sulla flangia partono in alto: ho girato di 180° il poligono, lo strato inferiore e la seconda flangia (per tenere allineati i fori dei perni); per questo la fessura radiale della seconda flangia sta dalla parte opposta di quella della prima.
- **FilamentSpool**: la flangia smontabile non è segnata come coperchio (`lid`): la bobina si vede chiusa, anche in galleria.
- **MakitaPowerSupply**: i due "side" (guide per la batteria) stanno sotto il fondo sui loro fori, profondi hm = 15,5 (fisso nel generatore); da quale estremità vada la punta a 60° non si ricava: l'ho messa verso il retro.
- **MakitaPowerSupply**: i due "side2" non hanno incastri: li ho incollati sulla faccia esterna di ciascuna guida, a filo del fondo e dall'inizio della guida; potrebbero andare sulla faccia interna o rovesciati.
- **Spool**: con i rinforzi, le prime `reinforcements` nervature vanno sulla flangia sinistra, le altre sulla destra (sono tutte uguali).
- **Folder**: la costola flex è lunga π·h e l'ho piegata a 180° con la linea media di raggio h, quindi le copertine distano circa 2h - t (37 mm con h = 20). Se h era inteso come spessore del dorso (semicerchio di diametro h) la costola risulterebbe compressa; ho seguito la lunghezza disegnata.
- **Folder**: mostrata in piedi come un libro, dorso a sinistra, copertina davanti verso chi guarda.
- **BottleTag**: il cartellino è mostrato orizzontale, appoggiato sulla spalla della bottiglia a 150 mm da terra, la parte lunga verso il davanti (nella foto pende inclinato in avanti).
- **AngledCutJig**: i triangoli piccoli sono girati (angolo retto a sinistra) perché i due piani formino la V della foto; i piani appoggiano sulle ipotenuse partendo dallo spigolo basso del triangolo (dove iniziano i fori, a u = 0).
- **OttoBody**: la testa (il coperchio della cerniera a baule) è mostrata chiusa e non è marcata come coperchio (lid): è la testa del robot, la galleria la toglierebbe. Se si vuole il pulsante coperchi, marcarla lid e aggiungere OttoBody a GALLERY_LIDS.
- **OttoBody**: il fondo è girato di 90° rispetto a IntegratedHingeBox perché i fori degli alberi dei servo (a u = 6 e x - 6) stiano a sinistra e a destra, dove vanno le gambe.
- **OttoBody**: i due supporti servo (60×14 e 54.4×14, con il foro 12×23 del servo) sono messi orizzontali contro i fianchi sinistro e destro, con il foro sopra il foro dell'albero nel fondo, il lato inferiore a 7 mm dal fondo (sopra le alette di un SG90 capovolto con l'albero nel fondo). Non hanno incastri: altezza e lato sono una stima.
- **PhotoFrame**: mostrato in piedi come appeso, dal davanti: fronte (Y 0…t), strato centrale con il passe-partout nella tasca (t…2t), base (2t…3t). Il passe-partout è centrato in larghezza e appoggiato sulla guida inferiore.
- **PhotoFrame**: lo strato centrale non diviso (middle_unsplit) non è raggiungibile dall'interfaccia (split_middle fisso a True); è comunque piazzato come la base, senza averlo provato.
- **PhotoFrame**: agli angoli a 45° del fronte diviso le code di rondine si sovrappongono di circa 13 mm² per angolo (lo stesso con tutte le orientazioni dei pezzi): sembra la tolleranza del generatore, non corretto.
- **CanStorage**: i fianchi "right" a X = larghezza e "left" a X = 0 (davanti verso −Y, dove escono le lattine); i pezzi interni seguono i fori dei fianchi (scivolo basso che sale verso il retro, scivolo alto che scende verso il retro con la tacca di caduta in fondo, barriera verticale davanti, retro con u dall'alto in basso).
- **CanStorage**: i tre spingitori (Pusher) sono messi nell'angolo tra scivolo basso e retro, con le linguette nelle fessure a 0,15 / 0,5 / 0,85 della larghezza; la cornice locale (origine sotto la linguetta del lato A) è ricavata dal disegno di DrawPusher.
- **CanStorage**: gli stabilizzatori (con piedi "š") sono appoggiati a terra all'interno dei piedi: i due corti (Stabilizer 1, 2) davanti, i due lunghi (3, 4) dietro, perché le lunghezze corrispondono ai piedi anteriore e posteriore; da confermare.
- **Dispenser**: il coperchio è fatto di due strati, "Lid bottom" (x × y, bordi lisci) dentro l'apertura e "Lid top" (bordi sporgenti di t) sopra le pareti; entrambi segnati come coperchio. È la mia lettura dei due pezzi, il generatore non lo dice.
- **Dispenser**: con bottomheight > 0 il pavimento sta a hb − spaziatura dei piedi "š" sopra la linea di base, come i fori delle pareti; i pannelli frontali cominciano sopra la fessura (hb + t + slotheight).
- **CoinDisplay**: pareti e coperchio del cubo segnati come acrilico trasparente (`clear=True`, come DisplayCase), altrimenti il supporto della moneta non si vede; il fondo e il supporto restano nel materiale scelto. La foto è tutta in acrilico.
- **CoinDisplay**: il supporto è centrato sul fondo (i fori lo dicono, una volta tolto lo scarto di t della callback); il piano inclinato sale verso il retro; dei due piatti quello con il foro sta sopra, a filo con lo scivolo, quello pieno sotto (l'incastro F è profondo 2t apposta).
- **Display**: l'inclinazione non è data dal generatore. Ho messo il ripiano perpendicolare al pannello (la fessura alta 1,3t lascia circa 17° di gioco), appoggiato sul bordo inferiore della fessura, con un terzo davanti al pannello e il resto dietro fino a terra; il bordo posteriore in basso del pannello appoggia a terra. Ne viene circa 22° con i valori di default. La proporzione 1/3 è una scelta mia.
- **CarbonFilter**: costole, binari e piastre seguono i fori: le costole delle falde sinistre ai fori disegnati dal primo bordo della piastra di fondo, quelle delle falde destre ai fori specchiati (3t di lato, così si incrociano); i binari delle falde destre sono girati (u da Y = y) perché i loro fori combacino con quelle costole.
- **CarbonFilter**: le costole esterne poggiano a terra: il loro incastro f(4t) è rivolto verso l'alto nella piastra di fondo e il piede arrotondato sta 3t sotto di essa. La punta delle costole esterne di bordo arriva alla barra laterale (verificato: X ≈ t).
- **CarbonFilter**: i "side holders" (parallelogrammi 10 mm) li ho messi sulle facce interne delle piastre di testa, fuori dallo strato di carbone, dal fondo fino sotto i binari (l'altezza combacia esattamente): a reggere i bordi della rete. Posizione dedotta, non scritta nel generatore.
- **CarbonFilter**: gli stabilizzatori superiori li ho messi orizzontali tra le due costole interne di una tasca, alla quota dove la distanza tra i loro bordi interni è l (le tacche agganciano le costole, che sono 3t sfalsate come le tacche); su min(3, ribs) coppie per tasca, scelte distribuite (int((m + 0,5)·ribs/n)). Quota, orientamento e coppie sono una mia ricostruzione.
- **OttoLegs**: le due gambe affiancate lungo Y a 10 mm (OTTOLEGS_FOOT_GAP), ciascuna sul suo piede; il corpo dell'Otto (altro generatore) non c'è.
- **OttoLegs**: l'asse della caviglia passa per il foro della parete posteriore e per il centro dell'intaglio del frontale (7 mm sopra il fondo della gamba), allo stesso livello dei fori delle staffe (15 mm sopra il piede, 20 mm lungo): gamba dritta, piede piano.
- **OttoLegs**: la staffa col foro grande (braccetto del servo) davanti, dalla parte dell'intaglio; quella col foro per il bullone dietro, dalla parte del foro posteriore.
- **OttoLegs**: la piastrina liscia (eeee, foro da 1,5) l'ho messa dentro, subito sotto il coperchio, come foro pilota sotto quello da 2,3; potrebbe andare sopra.
- **OttoLegs**: il ripiano interno e la mensolina del frontale stanno a 25 mm (dai fori); il fianco con l'asola rettangolare (cavi) è rivolto verso l'altra gamba.
- **OttoLegs**: i due anelli del servo (servoring) li ho messi all'esterno delle staffe del braccetto, centrati sul foro: il generatore non dice dove vanno.
- **Hook**: appeso al muro (WALLS, muro a Y = t): pannello posteriore in piedi, gancio verso −Y.
- **PoleHook**: mostrato in piedi sulla manopola. Ordine della pila dal basso: i due strati della manopola con l'esagono, quello col foro, poi i dischi 8, 7 (quello con la fessura per la fascetta), 6 e in cima quello con i fori dei forchettoni. L'ordine fra i dischi è ipotizzato (7 e 8 hanno il foro più largo e girerebbero liberi).
- **PoleHook**: i cinque forchettoni: i due interi all'esterno, quello corto con le dita al centro, i due lisci in mezzo (tre file di fori a −2t, 0, 2t; i tre strati del fermo stanno nello spazio fra i due interi).
- **PoleHook**: il fermo a L gira sul perno in cima ai bracci alti: un braccio sulla retta verso il centro del palo (lungo esattamente fino alla superficie del palo), l'altro in su sopra l'apertura. Potrebbe essere al contrario.
- **PoleHook**: i due dischetti da ww chiudono il perno fuori dai forchettoni interi (ipotesi).
- **RoyalGame**: le linee blu del tabellone e delle pedine sono incisioni (lo dice la descrizione): il tabellone e le pedine sono pieni, resta tagliato solo il foro di aggancio del coperchio; in 3D le incisioni non si vedono.
- **RoyalGame**: il pannello di testa nlmE è il coperchio scorrevole (un coperchio a slitta girato di fianco): bordo E davanti, dita l nei fori L della parete posteriore, bordo n sotto il bordo N del tabellone, m sopra il bordo M del fondo. Ricavato dagli accoppiamenti dei bordi.
- **RoyalGame**: pedine e dadi disposti davanti alla scatola. Ogni dado: due triangoli incastrati a croce (uno dritto lungo X, l'altro capovolto lungo Y, i fondi delle fessure a contatto), appoggiato sullo spigolo di base e alzato di circa 0,8 mm perché la punta dell'altro triangolo non vada sotto il piano.
- **AgricolaInsert**: disposizione nella scatola del gioco ricavata dai numeri di render() e dalla foto: vassoio delle carte lungo Y a sinistra, poi la fascia di due file (scatola stanze legno, stanze pietra, brughiera, cavalli, nell'ordine di disegno), poi due colonne di tre scatole giocatore; sopra stanze e brughiera i quattro vassoi superiori (quello da 4 scomparti accanto alle carte, i due lunghi 145 accanto, quello di cibo/fuoco di traverso in fondo). I vassoi superiori coprono le scatole basse: si vedono con la vista esplosa.
- **AgricolaInsert**: l'angolo ribassato della scatola della brughiera è verso la scatola dei cavalli; le scatole giocatore hanno la testata verso Y = 0, distanziate di 218/3.
- **AgricolaInsert**: la scatola delle stanze ha l'apertura inclinata in alto (come dice la descrizione); la parete alta è disegnata capovolta (bordo e in alto).
- **AgricolaInsert**: un solo separatore di legno, appeso nella nona fessura dal fondo (posizione arbitraria); i separatori mobili dei vassoi a intervalli uguali.
- **AgricolaInsert**: il vassoio delle carte non ha fondo (il generatore non lo disegna): poggia sul fondo della scatola del gioco.
- **NightLightBox**: il coperchio del vano elettronica ha 1,5t lisci prima del bordo f; li ho messi verso il retro (Y 85..89,5 con i valori di default) perché verso il davanti si sovrapporrebbe di 2 mm al diffusore. Da confermare.
- **NightLightBox**: tavole e diffusore appoggiano sul pavimento (fondo a filo del piano); le orecchie restano 0,3 mm sopra il fondo delle fessure dei fianchi. Con `hooks` la cima dei ganci supera di 0,2 mm il bordo dei fianchi e tocca il coperchio.
- **NightLightBox**: il retro è messo visto da fuori, quindi i fori BackExtraHoles (x misurata da sinistra guardando il retro) risultano a destra guardando la scatola dal davanti.
- **NightLightBox**: le due guide (2t × t) attraversano il foro quadrato dei fianchi: metà nello spessore del fianco e metà dentro la scatola, davanti alla cima del diffusore.
- **NightLightBox**: i perni del coperchio cadono negli occhi della cerniera dei fianchi (u del coperchio = Y); il coperchio copre Y -t..y-t, lasciando t aperto sul retro per la rotazione.
- **TriangleLamp**: ogni pezzo è disegnato due volte, quindi le ho interpretate come due lampade identiche, messe una accanto all'altra a 30 mm, in piedi sulla parete dell'ipotenusa con lo schermo davanti. Potrebbero anche essere pensate da appendere o da accoppiare schiena contro schiena.
- **TriangleLamp**: lo schermo è a filo del bordo anteriore delle pareti, appoggiato sui triangolini d'angolo (che sono nei fori a 1,5t dal bordo).
- **BookHolder**: il supporto posteriore parte a bottom_support da terra (dove sono i fori), non dal pavimento.
- **BookHolder**: il bordo frontale (ledge) sta in piedi davanti al fondo del libro, con il bordo F attorno alle dita del fondo, e sporge di ledge_height sopra la sua faccia superiore.
- **Shadowbox**: l'oggetto sta in piedi come una cornice (x in larghezza, y in altezza), appoggiato sulla parete inferiore della cassa; i telai sono impilati contro la cornice frontale senza lo spessore della carta; l'anello porta-LED è a filo del retro della cassa.
- **Shadowbox**: i pannelli di fondo (back_edge E, f, F, h) sono segnati come coperchi; con 'h' il pannello sta nei fori, nella stessa posizione degli altri casi.
- **FatBallDispenser**: l'altezza della gabbia non è un parametro: ho preso 2,4 diametri di pallina fra pavimento e soffitto (180 mm con i default; nella costruzione di riferimento i pali sono di 190 mm). I pali vanno dal fondo del pavimento alla cima del soffitto.
- **FatBallDispenser**: le pareti del balcone sono rettangoli con la faccia esterna sul bordo esterno del pavimento; gli smussi da carteggiare non sono modellati, quindi agli spigoli si sovrappongono all'interno.
- **FatBallDispenser**: il bordo esterno della base di ogni tegola è sullo spigolo superiore esterno della piastra del tetto; senza lo smusso la base entra di circa 2,5 mm nella piastra.
- **FatBallDispenser**: lo spaziatore è alla quota del soffitto (il soffitto scorre nella sua U), la staffa sotto, con il labbro sotto il soffitto; l'apertura della U è verso sinistra (-X).
- **Kamishibai**: i pannelli laterali sono a X -3t..-2t (seguendo i fori L del fondo), con le due piastre interne dietro (X -2t..0) e un piolo in ogni foro; le strisce delle profondità extra a X -t..0. Il primo pezzo disegnato di ogni coppia va a destra (simmetrici).
- **Kamishibai**: le due ante sono aperte di 100° (KAMISHIBAI_DOORS_OPEN) attorno ai perni negli occhi della cerniera dei piani; l'asse del perno è ricavato dal contorno dell'anta.
- **Kamishibai**: ordine e orientamento dei dischi delle serrature ricavati dalle istruzioni: pomello ed esterno ruotati di un quarto perché i fori laterali si allineino con quelli dell'anta; il lato tondo del disco interno sopra l'anta destra; il lato tondo dei "locker" verso le strisce. I dischi tagliati dall'anta sono ricavati dal contorno del foro (i quadrati magenta non sono tagli, quindi sono dischi pieni).
- **Kamishibai**: la chiave è appesa al piolo sul pannello posteriore tramite il suo foro.
- **Kamishibai**: la ricetta lavora con Z = 0 sulla faccia superiore del fondo e alla fine alza tutto di t, così l'oggetto appoggia a terra.
- **Matrix**: il generatore chiama "Top" il telaio con la finestra e "Bottom" il fondo: l'ho messo in piedi come un quadro, Top davanti (verso chi guarda), Bottom dietro con il foro a serratura in alto. Tra Top e il telaio di montaggio (sui suoi fori nei muri) ho impilato, dal davanti: plexiglass (spesso `plexiglass_thicknes`, trasparente), le due griglie LED, il PCB; l'ordine viene dal calcolo `sandwich_height` del generatore, non da istruzioni esplicite.
- **Matrix**: tutto è sollevato di t perché il muro inferiore poggi a terra (ClosedBox invece lascia il fondo sotto Z = 0).
- **LaserClamp**: la parte superiore è mostrata chiusa (il distanziale in cima alla sua asola, ganasce a `minheight`), come nella foto con gli elastici; l'oggetto è tutto sollevato di maxheight − minheight perché l'asta della parte superiore tocchi terra. La piastra davanti e la parte inferiore dietro sono una scelta: il generatore non dice quale faccia guarda verso chi usa la pinza.
- **LaserClamp**: la piastra arrotondata ha i fori 0,1 mm più in alto di quelli della parte inferiore (il `burn` dei due contorni): messa alla stessa quota della parte inferiore.
- **Clock**: le gambe anteriori sono incollate dietro la piastra principale, nel gioco di t che i bordi a gradino dei ripiani lasciano; il ripiano inferiore poggia sulle spalle delle gambe, la colonna centrale passa nella sua tacca fino alla faccia superiore del ripiano alto. Dedotto dalle misure (larghezze e altezze coincidono), il generatore non lo dice; la quota delle spalle è ricalcolata dal `polyline` di `frontLegs` (se cambia, va aggiornata `_clock_frame`).
- **SevenSegmentClock**: i separatori sono messi con lo stesso schema di SevenSegmentPattern (stesse linee di fori, la seconda metà ruotata di 180°), una cifra ogni 0,6·height più 0,1·height dopo la seconda, come in `backCB`; delle 8 copie per lunghezza le due di ogni cifra sono prese in ordine (sono identiche). `_sevensegmentclock_digit` duplica il ciclo di SevenSegmentPattern: si può far usare anche a quella ricetta.
- **SevenSegmentClock**: sollevato di t perché il muro inferiore poggi a terra.
- **PizzaShovel**: i fianchi a cuneo poggiano sul lato dritto, la pala sui loro fori t sopra il pavimento (spazio per il nastro sotto) e sporge di y/2 davanti alle loro punte; il bordo dei fianchi con le dita va verso la metà posteriore della pala (quella con le dita `f`). Dietro, a t di distanza (dove il nastro gira attorno alla pala), la traversa da 40; sopra, `grip_height` più in alto, quella da 80, con i 40 mm dei fori del manico verso il fondo.
- **PizzaShovel**: manico: i tre strati alti tra le traverse (i due esterni con le dita nei fori), i due strati più bassi all'esterno, spostati di 10 mm in avanti così che le estremità tonde siano concentriche (bordo arrotondato rientrato di t tutto attorno). Lo spostamento è dedotto, non indicato.
- **PizzaShovel**: lo spingitore è appoggiato piatto a metà della pala (striscia inferiore sul nastro, superiore con le maniglie sopra, maniglie verso il manico); nella foto la parte con le maniglie è sollevata e appoggiata più indietro. Lo spessore della carta tra le due strisce è ignorato.
- **BottleStack**: con "double" il generatore non dice come si montano le due basi. Ho dedotto questo: la seconda base (frontali con le fessure doppie e traverse corte) sta dentro la prima, con i frontali a 0,5·t da quelli della prima, centrata in profondità. Le sue fessure profonde (2t) passano sopra le traverse lunghe e quelle normali tengono le traverse corte; è spostata di una bottiglia lungo X, così il porta-bottiglie è largo una bottiglia in più. Può allungarsi fino al doppio, ma non so se sia proprio l'uso previsto ("combined to up to double the width").
- **BottleStack**: senza "double" ci sono solo i due frontali e le traverse lunghe, come nella foto senza bottiglie; i frontali stanno sulle tacche delle traverse, a t dalle estremità arrotondate.
- **CoffeeCapsuleHolder**: è montato in verticale contro il muro (piastra posteriore sul muro, ingresso rotondo in alto). Il generatore dice che può stare anche capovolto sotto una mensola, come nella foto, ma ho scelto il muro. Per questo c'è un pannello forato dietro (`WALLS`, muro a Y = 3t, o 2t senza piastra posteriore), anche se l'oggetto si avvita e non si appende.
- **Stachel**: gli strati sono impilati così: quello con il foro più piccolo (ri − 20, il piede del flauto ci si appoggia) sotto, quello con le asole in mezzo, quello normale sopra. Ho seguito l'ordine di disegno e la foto. La pila è sollevata di 150 mm (`STACHEL_POLE`, lunghezza inventata) perché il palo arrivi a terra.
- **Stachel**: il centro del foro del palo è calcolato ripercorrendo `layer()`: il braccio è inclinato di 5° perché l'arco dell'anello è di 355°. Se il generatore cambia, `_stachel_pole_centre` va aggiornata.
- **JointPanel**: i pezzi sono messi in piano, uno accanto all'altro, come se il pannello fosse intero: le code di rondine (1,5 mm) si vedono appena. Con "separate" sono messi uniti lo stesso.
- **AirPurifier**: l'ho messo in piedi con il flusso d'aria verticale (filtri orizzontali sopra e sotto, come nella foto): le pareti che il generatore chiama "top" e "bottom" diventano davanti (con le aperture per infilare i filtri) e dietro, i ventilatori sui fianchi sinistro e destro. Tutto è alzato di t perché il telaio esterno inferiore stia a terra.
- **AirPurifier**: con i telai divisi le quattro strisce di ogni telaio sono in ordine davanti, sinistra, destra, dietro (davanti e dietro lunghe x, i fianchi tra di loro sulle code di rondine); quale delle due strisce laterali sia la sinistra è indifferente (sono uguali).
- **Ramp**: i triangoli (rectangularTriangle non è registrato come primitiva, quindi senza etichetta) sono riconosciuti per ordine: il primo pezzo sono i due fianchi, un eventuale pezzo senza etichetta dopo sono i rinforzi interni, centrati sui fori a k·x/(n + 1).
- **CoinBankSafe**: sportello chiuso, arretrato di 1,25t dal fronte e a 0,1t dai fianchi, ricavato dalla posizione dei fori della cerniera (1,75t dal fronte) e dalle linguette; cerniera sul fianco sinistro, barra di blocco sul destro.
- **CoinBankSafe**: ogni perno, dal fronte: manopola ondulata, disco con i numeri, disco del foro dello sportello, distanziale, disco a D, poi la punta del perno; il disco a D è girato con il lato tondo verso la barra (chiuso). La rotazione dei dischi coi numeri e il verso del perno piatto (spessore in verticale) sono arbitrari.
- **CoinBankSafe**: i dischi ritagliati che il generatore chiede di non buttare restano dove lavorano: quelli della cerniera (incollati sulle linguette dello sportello) nei fori di coperchio e fondo, quelli dei perni nei fori dello sportello. polygons_of li scarterebbe come sfrido, quindi li ricavo a parte dai loro tracciati.
- **CoinBankSafe**: la scatola sta sui piedini dei bordi "s" (linea di base 4t sopra terra); sotto lo sportello, davanti, tra i piedini resta aperto, come da generatore.
- **Shoe**: il bordo flessibile della striscia superiore è disegnato lungo a·(r − t)/stretch, ma lo piego sull'arco di raggio r della sua faccia inferiore: le strisce del flex sono distribuite sull'arco, la lunghezza non torna esattamente. L'origine di fianchi e striscia è presa t dentro l'angolo del contorno (margine/spaziatura dei bordi): verificata a occhio.
- **PaperBox**: il contorno unico è tagliato in pannelli lungo le linee di piega (calcolate dal percorso, non disegnate) e ripiegato; la carta ha lo spessore del materiale scelto (3 mm di default, irrealistico), quindi agli angoli il risvolto del coperchio compenetra le linguette di colla e i risvolti dei fianchi di uno spessore.
- **PaperBox** (widebox): i risvolti del bordo dei fianchi (lid_sides) li ho piegati di 180° verso l'interno, incollati sulle linguette di colla del davanti e del dietro, che stanno contro l'interno dei fianchi; potrebbero invece restare orizzontali come appoggio del coperchio.
- **PaperBox** (tuckbox): le pareti girano davanti → fianco destro → dietro → fianco sinistro, la linguetta di colla dentro il fianco destro; le alette antipolvere dei fianchi piegate in dentro sotto il coperchio e sopra il fondo; il coperchio (sul bordo del retro) e il fondo hanno il risvolto infilato dentro il davanti. Coperchio chiuso e segnato come coperchio.
- **TrafficLight**: i fianchi sono disegnati dall'alto in basso (u = 0 in cima), ricavato dal bordo S: ogni dente di schermo ha il suo lato a dita (che regge lo schermo) verso u minore, quindi lo schermo sta sopra ogni luce come nella foto. Il frontale sta nei fori a d − 2t dal bordo anteriore dei fianchi.
- **TrafficLight**: le finestre colorate (dischi di diametro h − 2t, uguale al foro del frontale) sono messe dentro il foro, nello spessore del frontale, e mostrate come acrilico trasparente (clear): nella realtà forse sono incollate dietro il frontale.
- **TrafficLight**: versione affiancata (upright = false): le pareti verticali trapezoidali stanno con il lato corto (d) in basso e il lungo (d + s) in alto, sotto il piano "top" che è più profondo di s; le due pareti col bordo back_edge (l'ultima del ciclo e quella disegnata a parte, "mirror") ai due estremi.
- **TrafficLight**: il fondo (bottom wall / bottom) sta sotto Z = 0 (Z −t … 0), come i fondi di altre ricette (BirdHouse).
- **Sphere**: ogni spicchio è curvato a mezzo meridiano di raggio R (faccia interna), a strisce piatte ogni 5° tangenti alla sfera: è un osoedro, gli spicchi vicini si toccano lungo i bordi. Il bordo del foro inferiore poggia sul pavimento (centro a R·cos(u_bottom/R) + t); la sfera è pensata come lampada appesa, ma così sta in piedi come nell'illustrazione.
- **Sphere**: la posizione di ogni spicchio sul foglio è calcolata dai valori del generatore (halfBellyLens, x_rightGoreBottom, u_goreBottom, passo bellyLens + 2·tab_width + 30, partenza a (−halfBellyLens, 30), burn): se il generatore cambia disposizione, la ricetta va aggiornata.
- **Sphere**: con cable_hook i ganci proseguono piatti oltre il foro superiore, verso l'asse, e si sovrappongono tra loro sopra il foro: nella realtà si piegano attorno al cavo.
- **OttoSoles**: ogni suola è fatta di due metà a L disegnate una dopo l'altra (ruotate di 45° sul foglio): ho preso due metà consecutive per suola, la seconda girata di 180° attorno al centro del telaio, con i tenoni a coda di rondine che si incontrano negli angoli opposti all'angolo smussato intero. La posizione dell'angolo è ricavata dal lato smussato verticale di ogni pezzo sul foglio. Le suole sono affiancate lungo X a 10 mm (OTTOSOLES_GAP), appoggiate a terra, non sotto i piedi di OttoLegs.
- **LaptopStand**: i due triangoli stanno sulle diagonali dell'impronta (quadrata, lato l_depth·cos(angle)) e si incrociano al centro della base; quello con la fessura sotto va dal fondo a destra al davanti a sinistra, quello con la fessura sopra (disegnato girato di 180°) dal fondo a sinistra al davanti a destra; i labbri davanti, le estremità alte dietro. La distribuzione destra/sinistra dei due è una scelta mia.
- **LaptopStand**: aggiunto TURN["LaptopStand"] = 25 perché nella galleria, vista dall'angolo, un triangolo si vede di taglio; il verso (25 o −25) non l'ho potuto verificare nell'app.
- **PhoneHolder**: il frontale ha la faccia posteriore sull'ipotenusa dei triangoli laterali (le dita dell'ipotenusa sporgono in avanti nei suoi fori); i triangoli fuori dalla larghezza del telefono (X −t … 0 e w … w + t); il retro dietro il cateto verticale. I due triangoli sono disegnati in un solo pezzo (num = 2, il secondo girato di 180°): separati con lo stesso sistema di AngledCutJig.
- **PhoneHolder**: i supporti inferiori sono messi con la linea del loro bordo a dita sulla faccia posteriore del frontale, centrati sui fori (margin e w − margin), il punto di partenza del disegno sotto l'estremo alto del bordo a dita, a (bottom_margin + tab_size)·sin(angle) dal davanti; il secondo è disegnato specchiato ma nel 3D è identico al primo.
- **Desksign**: la targa ha la faccia posteriore sull'ipotenusa dei due sostegni, i sostegni nella fascia di fori ai lati (X −t … 0 e width … width + t). Con feet tutto è sollevato dell'altezza dei piedini, ricavata dal pezzo (il bordo anteriore della targa resta sollevato da terra).
- **Atreus21**: tutti gli otto strati sono tagliati in un unico pezzo (nessun `move()`): li riconosco per posizione sul foglio (righe: keyholder e support, poi hotplug e bordo, per la metà sinistra e poi per la destra). Se il generatore cambia disposizione, l'ordinamento va rivisto.
- **Atreus21**: ordine degli strati dal basso: bordo (cornice distanziale), hotplug, support, keyholder in cima. Il support va incollato sotto il keyholder (lo dice il generatore); il bordo l'ho messo sotto perché lasci spazio ai socket hot-swap e ai fili (nella foto il lato inferiore mostra i cablaggi a vista). L'illustrazione `Atreus21.png` invece mostra il bordo in cima, come cornice attorno ai tasti: da decidere.
- **Atreus21**: le due metà sono affiancate dritte a 40 mm l'una dall'altra; nella foto sono ruotate a V.
- **FrameLoom**: montaggio dalla descrizione e dalla foto 2: piedi sotto il telaio con il collo (23 × t) nell'asola, i ganci sulla faccia superiore e il foro del perno verso il davanti (lato dei pioli numerati); il liccio in piedi (denti in su e in giù) con le maniglie infilate nei fori dei piedi e sporgenti ai lati. Il telaio è inclinato attorno al bordo anteriore finché le teste tonde dei piedi toccano il piano (circa 11° con le misure di default).
- **FrameLoom**: le misure fisse del generatore (larghezza cornice 15, offset delle asole 8, altezza denti del liccio 18, raggio del foro 4,25, collo del piede da u = 7) sono ricopiate nella ricetta: se cambiano nel generatore vanno aggiornate.
- **FrameLoom**: il liccio è mostrato in una sola posizione (verticale); nell'uso si gira di 90° per cambiare passo.
- **DiceTower**: la vaschetta è il coperchio "overthetop" capovolto, la torre appoggiata in fondo con fianchi e retro a play/2 dalle sue pareti (come nell'illustrazione); in uso potrebbe anche stare come coperchio sul davanti della torre.
- **AllEdges**: disposizione scelta (non c'è un montaggio): i 45 campioni distesi nell'ordine del foglio, in 5 colonne affiancate (la colonna unica del foglio è lunga più di 2 m), ciascuno con il suo bordo verso il fondo. Il disco delle cerniere a baule ("O", "o") è un pezzo a sé dentro l'occhio in cui gira: lo rimetto nel suo foro; i perni dei bordi a cerniera ("i", "j", "k") restano dove sono disegnati.
- **Tetris**: la seconda piastra è disegnata specchiata; la metto sopra come la prima (stesse coordinate locali). Le linee incise tra i blocchi non sono tagli e non compaiono.

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
- **SBCMicroRack**: un Raspberry Pi (misure e porte di un Pi 3B/4, su distanziali in ottone) sulla
  base e su ogni ripiano tranne quello in cima, come nella foto, con le porte centrate nelle finestre
  del fianco. La base non ha i fori di fissaggio (il Pi sta solo appoggiato), mentre il ripiano in
  cima li ha ma resta vuoto: segue la foto, non i fori.
- **Pezzi e campioni**: bullone delle manopole, alberi della GearBox, perni del planetario e del
  quadrilatero, asse della puleggia, motore della NemaMount (lungo quanto largo, come in NemaPattern).
- Colori dei nuovi materiali (bottiglie, barattoli, vinili, colori) da giudicare nell'app.
- **Arcade**: monitor nell'apertura (cornice nera profonda 20 mm sul piano interno dei pannelli, schermo `lcd` 15 mm all'interno) e, sulla tastiera che il generatore lascia senza fori, per ciascun giocatore un joystick e tre pulsanti: posizioni inventate.
- **MakitaPowerSupply**: batteria Makita 18 V (76 × 115 × 60, misure a occhio) sotto le guide, quindi sotto Z = 0 (il box sta in piedi sulle guide); cornice del modulo DSP5005 con schermo e manopola sopra la finestra del coperchio; boccole a banana nera e rossa e interruttore nei fori del frontale (l'interruttore solo se c'è l'alimentazione secondaria).
- **DrillGauge**: tre punte in piedi nella fessura dove la larghezza è la loro (una piccola, una media, la più grande), lunghezza 30 + 4·d inventata.
- **BottleTag**: una bottiglia ambrata (corpo 3.2 volte il collo, spalla a gradini, collo del diametro del foro interno min_diameter, tappo d'acciaio) perché il cartellino da solo non si capisce. Proporzioni inventate.
- **PhotoFrame**: la foto (carta 0.3 mm) dietro il passe-partout, dentro la tasca, visibile dalla finestra.
- **PhotoFrame**: si appende al muro (fori di montaggio in alto sulla base): se si vuole il pannello forato, il muro è a Y = 3t (faccia posteriore della base). Non l'ho aggiunto a WALLS: un pannello Skådis dietro una cornice sembra fuori luogo.
- **CanStorage**: lattine ("tin") distese di traverso, dove le mette il disegno di debug del generatore: metà sullo scivolo basso a partire dalla barriera, il resto sullo scivolo alto ma solo quante ci stanno prima della tacca di caduta (con i default 6 + 4 = 10 su 12, non tutte canNum).
- **Dispenser**: una pila degli oggetti da distribuire ("cards"), spessi quanto la fessura, 1 mm lontani dalle pareti, fino a due terzi dell'altezza.
- **CoinDisplay**: la moneta ("brass"), spessa 2 mm, nel foro del piatto superiore, appoggiata su quello pieno.
- **Display**: una pila di volantini ("paper") larga x − 4, alta h, spessa 3 mm, in piedi sul ripiano contro il pannello.
- **PoleHook**: il palo agganciato (grip-red, lungo 3 diametri) nella U dei forchettoni, e il perno d'acciaio del fermo.
- **Shadowbox**: lo strato di carta bianco di fondo (0,2 mm) dietro l'ultimo telaio.
- **FatBallDispenser**: i pali (dowel) agli angoli dei poligoni, attraverso pavimento e soffitto, e due palline di grasso ("cardboard", fatte di 12 fette ciascuna) impilate sul pavimento. Il colore "cardboard" è una scelta di ripiego.
- **Kamishibai**: una pila di fogli (metà di SheetsStackDepth) in piedi contro la parete frontale.
- **Matrix**: PCB nero spesso `height_pcb` dietro le griglie e un LED bianco (mezzo pixel di lato, 1,6 mm) al centro di ogni cella della griglia anteriore; misure dei LED inventate.
- **Clock**: movimento al quarzo nero 56 × 56 × 16 (al massimo Re/2) dietro la piastra, perno in ottone nel foro e tre lancette (ore, minuti, secondi rossa) nell'incavo dell'anello alle 10:10; forme e spessori inventati.
- **PizzaShovel**: nastro di carta da forno (0,3 mm, largo x − 3 come lo spingitore) sopra la pala (interrotto sotto la striscia inferiore dello spingitore) e sotto; senza manico (`grip_length` = 0) un tondino di legno spesso `grip_height`, lungo 250 mm dietro le traverse, tra le due traverse dove sono le viti.
- **BottleStack**: bottiglie di birra stese nelle conche, con il collo verso il davanti e il corpo centrato sul porta-bottiglie; una per conca e una sopra, nella gola centrale (come nella foto). La lunghezza (5,15·r1) è inventata, il generatore non la dà.
- **CoffeeCapsuleHolder**: una colonna di capsule tipo Nespresso per ogni fessura, un colore per colonna, impilate dal fondo della fessura. Il coperchio sta nella piastra centrale, il corpo (profilo inventato, lungo 0,75·lid_size) esce dalla piastra davanti. Ci sono anche le teste delle quattro viti nei fori grandi della piastra davanti.
- **Stachel**: il palo è un tondino di legno (`dowel`) nel foro del braccio, da terra fino a 20 mm sopra la pila.
- **AirPurifier**: un ventilatore (cornice d × d profonda fan_width con il foro, mozzo e sette pale) contro l'interno di ogni foro, e i filtri come lastre bianche ("paper") spesse fh tra telaio esterno e interno, infilati dal davanti; misure del ventilatore a occhio.
- **PhoneHolder**: un telefono ("lcd", phone_width × phone_height × phone_depth) appoggiato sul frontale, il fondo bottom_margin più su lungo il frontale, nei ganci dei supporti.
- **Atreus21**: su ogni foro del keyholder la parte superiore dell'interruttore (14,6 mm, alta 6) e un tasto alto 8 mm (18 mm, gradino a 15 mm), come per il Keypad. Niente viti agli angoli né microcontrollore.
- **DiceTower**: due dadi da 16 mm davanti alla torre, sulla vaschetta (o sul piano se manca), a distanze inventate.

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
- Misure esterne e distanza tra i pezzi: boxes.py, per passare dalle misure esterne a quelle
  interne, toglieva anche il "margine" del bordo impilabile, che contiene la distanza tra i pezzi
  sul foglio: allargando la distanza, gli impilabili (StackableBin, WallStackableBin, Crate con
  bordo impilabile…) si rimpicciolivano. Corretto nel bridge (`adjustSize` senza la distanza): le
  misure degli impilabili sono cambiate rispetto a prima di qualche decimo, ora sono quelle giuste.
  Un controllo su tutti i generatori (distanza 2 e 7 mm, con e senza misure esterne) non trova
  altri pezzi che cambino forma.

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
- Pezzi e campioni: compilati e avviati; da provare nell'app.
- "Varie" (53 modelli): compilati e avviati; da provare nell'app. LaptopStand è girato di 25° nella
  galleria (TURN) perché un triangolo non si veda di taglio: verificare il verso.
