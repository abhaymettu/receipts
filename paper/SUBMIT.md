# Submitting to arXiv (for Abhay; nothing here has been submitted)

1. Build and check: `tectonic paper/main.tex`, then open `paper/main.pdf` and read it once end to end.
2. Make the source bundle arXiv compiles itself (it runs pdflatex + bibtex, so include the `.bbl`):
   ```bash
   cd paper
   tectonic --keep-intermediates main.tex
   tar czf receipts-arxiv.tar.gz main.tex main.bbl refs.bib
   ```
3. Endorsement: a first cs.SE submission may need an endorser. Check at
   https://arxiv.org/auth/endorse after logging in; if asked, request one from someone who has posted in cs.SE.
4. Go to https://arxiv.org/submit, log in, start a new submission.
   - License: CC BY 4.0.
   - Primary category: **cs.SE** (Software Engineering).
   - Cross-lists: **cs.AI**, **cs.CL**.
5. Upload `receipts-arxiv.tar.gz`. Confirm the preview PDF matches `main.pdf` (9 pages, three tables, references).
6. Metadata:
   - Title: Claims Without Receipts: How Often Coding Agents' Reports Go Unbacked, and Why Receipt Rules Cannot Tell
   - Authors: Abhay Mettu
   - Abstract: paste the abstract from `main.tex` as plain text (replace `\%` with `%`, `$\kappa \approx 0$` with `kappa about 0`, `\texttt{...}` with the plain text, `` ``...'' `` with plain quotes).
   - Comments: `9 pages, 3 tables. Code and aggregate results: https://github.com/abhaymettu/receipts`
7. Submit before 14:00 US Eastern on a weekday to be announced that evening. Then add the arXiv id to the README.
