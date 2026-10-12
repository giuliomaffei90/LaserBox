# 3D: punti da rivedere

Annotazioni raccolte mentre facevo le viste 3D (mensole e scaffali, modelli da parete, motivi di fori,
pezzi di test, pezzi e campioni, prima metà di "Varie"), le decorazioni e l'esploso. Per ognuno: cosa ho fatto, perché è dubbio, cosa si può decidere.

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
- Pezzi e campioni: non compilati; da provare nell'app.
- "Varie", dall'Alimentatore Makita alla Mangiatoia per palline di grasso (27 modelli): non compilati;
  da provare nell'app. Restano da fare gli altri 27 del gruppo.
