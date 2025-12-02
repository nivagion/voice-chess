Struktura projekta
main.py – glavni ulaz u program, game loop, logika biranja strane, obrada glasovnih poteza i bot poteza.
always_on_voice.py – always-on VOSK listener koji stalno sluša mikrofon i vraća prepoznate fraze.
viewer.py – Pygame viewer za crtanje šahovske ploče i figura.
figures/ – PNG slike šahovskih figura (npr. Chess_plt60.png itd.).
models/ – VOSK modeli za prepoznavanje govora (npr. vosk-model-small-en-us-0.15/).


Kako radi pipeline (kratko)
1.	main.py pokreće igru i postavlja chess.Board
2.	viewer.py crta ploču u Pygame prozoru
3.	always_on_voice.py sluša mikrofon i vraća prepoznate fraze
4.	main.py normalizira izgovoreni tekst u UCI notaciju (npr. "pawn e two to e four" → e2e4)
5.	python-chess provjerava je li potez legalan i ažurira ploču
6.	viewer.py osvježava prikaz ploče nakon svakog poteza
7.	bot odigrava nasumični legalan potez i ciklus se nastavlja dok partija ne završi ili igrač ne kaže quit





## Features

- Glasovni unos poteza (npr. `pawn e two to e four`)
- Vizualni prikaz ploče preko Pygame-a
- Nasumični bot koji odigrava legalne poteze
- Highlight zadnjeg poteza na ploči

## Requirements

- Python 3.10+ (preporučeno)
- [`python-chess`](https://pypi.org/project/python-chess/)
- [`sounddevice`](https://pypi.org/project/sounddevice/)
- [`vosk`](https://pypi.org/project/vosk/)
- [`pygame`](https://pypi.org/project/pygame/)

Primjer instalacije (u virtualnom okruženju):

```bash
pip install python-chess sounddevice vosk pygame

Također trebaš VOSK model, npr. vosk-model-small-en-us-0.15, u folderu:

models/vosk-model-small-en-us-0.15