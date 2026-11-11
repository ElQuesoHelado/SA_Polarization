# Registro de referencias bibliográficas

**Actualizado:** 2026-11-10
**Uso:** contexto compartido para agentes y para el paper (`docs/doc.tex`).

Este registro es la fuente de verdad sobre la literatura del proyecto. Cada PDF local tiene una nota con cita completa, hallazgos citables, límites y uso previsto. Los agentes deben consultar este índice antes de citar o interpretar literatura; si se agrega, retira o reclasifica una referencia, actualizar el índice y la nota en el mismo cambio.

## Criterio de uso

- **Fuente principal:** Martínez-España et al. (2024) define la metodología de polarización afectiva individual (AP, AP_In, AP_Out, spread) que el pipeline adapta. Su resumen operativo también vive en `AGENTS.md`; esta nota lo amplía con detalle para el paper.
- **Referencias de contexto:** caracterizan el fenómeno (polarización, echo chambers, SA político) o la técnica (Transformers, RoBERTuito, encuestas). **No son benchmarks numéricos**: plataforma, idioma, unidad de análisis, periodo y constructo difieren.
- **Regla de transferencia:** no comparar magnitudes entre estudios sin armonizar definición, población y corte. Citar cifras solo con su tabla/sección de origen.
- Las referencias descartadas se conservan para trazabilidad, con el motivo del descarte.

## Biblioteca de PDFs del paper

**Criterio de numeración:** orden de importancia en `docs/doc.tex` (núcleo metodológico → contexto peruano → antecedentes de polarización/SA → surveys y contexto general). La columna `IEEE` es el número de referencia en la bibliografía del paper (orden de cita). Los números 08 y 14 quedan reservados para trabajos citados sin copia local; no se reutilizan.

| # | Clave `.bib` | IEEE | Archivo | Estado |
|---:|---|---:|---|---|
| 01 | `polariz` | [5] | `pdfs/01.martinez-espana-2024.pdf` | Disponible |
| 02 | `robertuito` | [13] | `pdfs/02.robertuito-2022.pdf` | Disponible (arXiv v3) |
| 03 | `wagner2021affective` | [20] | `pdfs/03.wagner-2021.pdf` | Disponible (preprint OSF CC-BY) |
| 04 | `Ayma2024` | [7] | `pdfs/04.ayma-2024.pdf` | Disponible |
| 05 | `CalizayaMilla2026` | [14] | `pdfs/05.calizaya-2026.pdf` | Disponible |
| 06 | `Ponte2022` | [9] | `pdfs/06.ponte-2022.pdf` | Disponible |
| 07 | `Mejia2024` | [10] | `pdfs/07.mejia-2024.pdf` | Disponible |
| 08 | `Carrera2026` | [8] | `pdfs/08.carrera-2026.pdf` | Sin copia local (Springer cerrado) |
| 09 | `Miehling2025` | [19] | `pdfs/09.miehling-2025.pdf` | Disponible |
| 10 | `bor2023` | [6] | `pdfs/10.bor-2023.pdf` | Disponible |
| 11 | `rodriguez2021sentiment` | [17] | `pdfs/11.rodriguez-ibanez-2021.pdf` | Disponible |
| 12 | `chaudhry2022sentiment` | [18] | `pdfs/12.chaudhry-2021.pdf` | Disponible |
| 13 | `rizk2023predicting` | [16] | `pdfs/13.rizk-2023.pdf` | Disponible |
| 14 | `pandey2025twitter` | [15] | `pdfs/14.pandey-2025.pdf` | Sin copia local (IEEE cerrado) |
| 15 | `Singh2026` | [4] | `pdfs/15.singh-2026.pdf` | Disponible |
| 16 | `ANTONAKAKI2021114006` | [11] | `pdfs/16.antonakaki-2021.pdf` | Disponible |
| 17 | `10.1145/3446132.3446424` | [12] | `pdfs/17.utitiaj-2021.pdf` | Disponible |
| 18 | `afyare2025socialmedia` | [3] | `pdfs/18.afyare-2025.pdf` | Disponible |
| 19 | `statista2026` | [1] | — | Web; sin PDF |
| 20 | `ref1` | [2] | — | Web; sin PDF |

Los PDFs de trabajos no citados en `doc.tex` se conservan en `pdfs/contexto/`; los descartados, en `pdfs/Irrelevantes/`. Si se obtienen los números 08 o 14, guardarlos con el nombre indicado y actualizar el estado.

## Referencias activas

| ID | Cita | PDF local | Rol | Nota |
|---|---|---|---|---|
| `martinez-espana-2024` | Martínez-España, R.; Fernández-Pedauye, J.; Giner-Pérez de Lucía, J.; Rojo-Martínez, J. M.; Bakdid-Albane, K.; García-Escribano, J. J. (2024). *Methodology for Measuring Individual Affective Polarization Using Sentiment Analysis in Social Networks*. IEEE Access 12. DOI [10.1109/ACCESS.2024.3431999](https://doi.org/10.1109/ACCESS.2024.3431999) | `pdfs/01.martinez-espana-2024.pdf` | `principal` | [martinez-espana-2024.md](martinez-espana-2024.md) |
| `ayma-2024` | Ayma Quirita, V. A.; Cárdenas, J. D.; Aliaga, W.; Ayma Quirita, V. H.; Palacios, A.; Sierra, R. B. (2024). *Peruvian Presidential Debates in the Elections of 2021 in Twitter/X: A Sentiment Analysis Approach*. IEEE Access 12. DOI [10.1109/ACCESS.2024.3465503](https://doi.org/10.1109/ACCESS.2024.3465503) | `pdfs/04.ayma-2024.pdf` | `contexto-peru` | [ayma-2024.md](ayma-2024.md) |
| `robertuito-2022` | Pérez, J. M.; Furman, D. A.; Alonso Alemany, L.; Luque, F. (2022). *RoBERTuito: a pre-trained language model for social media text in Spanish*. LREC 2022. arXiv:2111.09453v3. DOI [10.48550/arXiv.2111.09453](https://doi.org/10.48550/arXiv.2111.09453) | `pdfs/02.robertuito-2022.pdf` | `modelo-sa` | [robertuito-2022.md](robertuito-2022.md) |
| `wagner-2021` | Wagner, M. (2021). *Affective Polarization in Multiparty Systems*. Electoral Studies 69, 102199. DOI [10.1016/j.electstud.2020.102199](https://doi.org/10.1016/j.electstud.2020.102199) | `pdfs/03.wagner-2021.pdf` (preprint OSF) | `polarizacion-sa` | [wagner-2021.md](wagner-2021.md) |
| `calizaya-2026` | Calizaya-Milla, S. E.; Santos, J.; Huanca Torres, F. A. (2026). *Fine-Tuning Monolingual Pre-Trained BERT Models for Sentiment Analysis in Peruvian Slang Contexts*. Applied Artificial Intelligence 40(1), e2641381. DOI [10.1080/08839514.2026.2641381](https://doi.org/10.1080/08839514.2026.2641381) | `pdfs/05.calizaya-2026.pdf` | `contexto-peru` | [calizaya-2026.md](calizaya-2026.md) |
| `utitiaj-2021` | Utitiaj, I.; Morillo, P.; Vallejo-Huanga, D. (2021). *Sentiment Analysis Tool for Spanish Tweets in the Ecuadorian Context*. ACAI 2020, ACM. DOI [10.1145/3446132.3446424](https://doi.org/10.1145/3446132.3446424) | `pdfs/17.utitiaj-2021.pdf` | `contexto-idioma` | [utitiaj-2021.md](utitiaj-2021.md) |
| `ponte-2022` | Ponte Torrel, V. H. (2022). *La campaña peruana en Twitter. Análisis de la polarización afectiva durante la segunda vuelta de las elecciones generales 2021*. Cuadernos.info 53. DOI [10.7764/cdi.53.49539](https://doi.org/10.7764/cdi.53.49539) | `pdfs/06.ponte-2022.pdf` | `contexto-peru` | [ponte-2022.md](ponte-2022.md) |
| `mejia-2024` | Mejía Navarrete, J. (2024). *Polarización política en el Perú, 2000–2023*. *Discursos del Sur*, 14, 236–269. DOI [10.15381/dds.n14.29843](https://doi.org/10.15381/dds.n14.29843) | `pdfs/07.mejia-2024.pdf` | `contexto-peru` | [mejia-2024.md](mejia-2024.md) |
| `miehling-2025` | Miehling, E.; Dakota, D.; Kübler, S. (2025). *Investigating Polarization in YouTube Comments via Aspect-Based Sentiment Analysis*. RANLP 2025. [ACL Anthology](https://aclanthology.org/2025.ranlp-1.83/) | `pdfs/09.miehling-2025.pdf` | `youtube-sa-polarizacion` | [miehling-2025.md](miehling-2025.md) |
| `wu-2021` | Wu, S.; Resnick, P. (2021). *Cross-Partisan Discussions on YouTube: Conservatives Talk to Liberals but Liberals Don't Talk to Conservatives*. ICWSM 2021 15(1). DOI [10.1609/icwsm.v15i1.18105](https://doi.org/10.1609/icwsm.v15i1.18105) | `pdfs/contexto/wu-2021.pdf` | `youtube-sa-polarizacion` | [wu-2021.md](wu-2021.md) |
| `shevtsov-2023` | Shevtsov, S.; O’Connor, A.; O’Hagan, M.; Carley, K. M. (2023). *What Tweets and YouTube comments have in common? An analysis of social media dynamics during the 2020 US Presidential Election*. PLOS ONE 18(4), e0270542. DOI [10.1371/journal.pone.0270542](https://doi.org/10.1371/journal.pone.0270542) | `pdfs/contexto/shevtsov-2023.pdf` | `youtube-sa-polarizacion` | [shevtsov-2023.md](shevtsov-2023.md) |
| `elfes-2026` | Elfes, T.; Bastos, M.; Aiello, L. M. (2026). *Measuring narrative polarization in online discourse*. PNAS Nexus 5(8), pgag270. DOI [10.1093/pnasnexus/pgag270](https://doi.org/10.1093/pnasnexus/pgag270) | `pdfs/contexto/elfes-2026.pdf` | `youtube-sa-polarizacion` | [elfes-2026.md](elfes-2026.md) |
| `tran-2022` | Tran, G. T. C.; Nguyen, L. V.; Jung, J. J.; Han, J. (2022). *Understanding Political Polarization Based on User Activity: A Case Study in Korean Political YouTube Channels*. SAGE Open 12(2). DOI [10.1177/21582440221094587](https://doi.org/10.1177/21582440221094587) | En acceso abierto (SAGE) | `youtube-sa-polarizacion` | [tran-2022.md](tran-2022.md) |
| `mall-2024` | Mall, R.; Nagpal, M.; Salminen, J. O.; Almerekhi, H.; Jung, S.-G.; Jansen, B. J. (2024). *Politics on YouTube: Detecting Online Group Polarization Based on News Videos’ Comments*. SAGE Open 14(2). DOI [10.1177/21582440241256438](https://doi.org/10.1177/21582440241256438) | En acceso abierto (SAGE) | `youtube-sa-polarizacion` | [mall-2024.md](mall-2024.md) |
| `falkenberg-2023` | Falkenberg, M.; Galeazzi, A.; Torricelli, M.; Di Marco, N.; Larosa, F.; Sas, M.; Mekacher, A.; Lamanna, W.; Zollo, F. (2023). *Affective and interactional polarization align across countries*. arXiv:2311.18535. DOI [10.48550/arXiv.2311.18535](https://doi.org/10.48550/arXiv.2311.18535) | `pdfs/contexto/falkenberg-2023.pdf` | `polarizacion-sa` | [falkenberg-2023.md](falkenberg-2023.md) |
| `bor-2023` | Bor, D.; Lee, B. S.; Oughton, E. J. (2023). *Quantifying polarization across political groups on key policy issues using sentiment analysis*. arXiv:2302.07775v2. | `pdfs/10.bor-2023.pdf` | `polarizacion-sa` | [bor-2023.md](bor-2023.md) |
| `rodriguez-ibanez-2021` | Rodríguez-Ibáñez, M.; Gimeno-Blanes, F.-J.; Cuenca-Jiménez, P. M.; Soguero-Ruiz, C.; Rojo-Álvarez, J. L. (2021). *Sentiment Analysis of Political Tweets From the 2019 Spanish Elections*. IEEE Access 9. DOI [10.1109/ACCESS.2021.3097492](https://doi.org/10.1109/ACCESS.2021.3097492) | `pdfs/11.rodriguez-ibanez-2021.pdf` | `polarizacion-sa` | [rodriguez-ibanez-2021.md](rodriguez-ibanez-2021.md) |
| `del-vicario-2016` | Del Vicario, M.; Vivaldo, G.; Bessi, A.; Zollo, F.; Scala, A.; Caldarelli, G.; Quattrociocchi, W. (2016). *Echo Chambers: Emotional Contagion and Group Polarization on Facebook*. Scientific Reports 6, 37825. DOI [10.1038/srep37825](https://doi.org/10.1038/srep37825) | `pdfs/contexto/del-vicario-2016.pdf` | `polarizacion-sa` | [del-vicario-2016.md](del-vicario-2016.md) |
| `arya-2026` | Arya, S.; Mittal, A.; Agarwal, A. (2026). *Sentiment Analysis of Regional Political Discourse in Indian Languages: Evidence from Bihar Assembly Election 2025*. Journal of Marketing & Social Research 3(2), ISSN 3008-0711. | `pdfs/contexto/arya-2026.pdf` | `polarizacion-sa` | [arya-2026.md](arya-2026.md) |
| `chaudhry-2021` | Chaudhry, H. N.; Javed, Y.; Kulsoom, F.; Mehmood, Z.; Khan, Z. I.; Shoaib, U.; Janjua, S. H. (2021). *Sentiment Analysis of before and after Elections: Twitter Data of U.S. Election 2020*. Electronics 10(17), 2082. DOI [10.3390/electronics10172082](https://doi.org/10.3390/electronics10172082) | `pdfs/12.chaudhry-2021.pdf` | `polarizacion-sa` | [chaudhry-2021.md](chaudhry-2021.md) |
| `rizk-2023` | Rizk, R.; Rizk, D.; Rizk, F.; Hsu, S. (2023). *280 characters to the White House: predicting 2020 U.S. presidential elections from twitter data*. Computational and Mathematical Organization Theory. DOI [10.1007/s10588-023-09376-5](https://doi.org/10.1007/s10588-023-09376-5) | `pdfs/13.rizk-2023.pdf` | `polarizacion-sa` | [rizk-2023.md](rizk-2023.md) |
| `antonakaki-2021` | Antonakaki, D.; Fragopoulou, P.; Ioannidis, S. (2021). *A survey of Twitter research: Data model, graph structure, sentiment analysis and attacks*. Expert Systems With Applications 164, 114006. DOI [10.1016/j.eswa.2020.114006](https://doi.org/10.1016/j.eswa.2020.114006) | `pdfs/16.antonakaki-2021.pdf` | `survey-sa` | [antonakaki-2021.md](antonakaki-2021.md) |
| `singh-2026` | Singh, M.; Panwar, S.; Choudhary, S. (2026). *Exploring advanced sentiment analysis techniques using deep learning architectures: a comprehensive survey*. Knowledge and Information Systems 68, 94. DOI [10.1007/s10115-026-02704-6](https://doi.org/10.1007/s10115-026-02704-6) | `pdfs/15.singh-2026.pdf` | `survey-sa` | [singh-2026.md](singh-2026.md) |
| `afyare-2025` | Afyare, A. A. A. (2025). *The Influence of Social Media on Political Discourse and Public Opinion*. Global Journal of Human-Social Science 25(F1), 45–77. | `pdfs/18.afyare-2025.pdf` | `contexto-general` | [afyare-2025.md](afyare-2025.md) |

## Mapa de citas en `docs/doc.tex`

| Clave BibTeX sugerida / usada | ID del registro |
|---|---|
| `polariz` | `martinez-espana-2024` |
| `Ayma2024` | `ayma-2024` |
| `wagner2021affective` | `wagner-2021` |
| `CalizayaMilla2026` | `calizaya-2026` |
| `Ponte2022` | `ponte-2022` |
| `Mejia2024` | `mejia-2024` |
| `Miehling2025` | `miehling-2025` |
| `Wu2021` | `wu-2021` |
| `Shevtsov2023` | `shevtsov-2023` |
| `Elfes2026` | `elfes-2026` |
| `Tran2022` | `tran-2022` |
| `Mall2024` | `mall-2024` |
| `Falkenberg2023` | `falkenberg-2023` |
| `bor2023` | `bor-2023` |
| `rodriguez2021sentiment` | `rodriguez-ibanez-2021` |
| `delvicario2016echo` | `del-vicario-2016` |
| `arya2026sentiment` | `arya-2026` |
| `chaudhry2022sentiment` | `chaudhry-2021` |
| `rizk2023predicting` | `rizk-2023` |
| `ANTONAKAKI2021114006` | `antonakaki-2021` |
| `Singh2026` | `singh-2026` |
| `robertuito` | `robertuito-2022` |
| `Carrera2026` | `carrera-2026` |
| `pandey2025twitter` | `pandey-2025` |
| `10.1145/3446132.3446424` | `utitiaj-2021` |
| `afyare2025socialmedia` | `afyare-2025` |
| `statista2026` | `statista-2026` |
| `ref1` | `aden-2026` |

## Referencias descartadas (`pdfs/Irrelevantes/`)

Se conservan solo para trazabilidad; no usar como sustento del paper sin una decisión explícita.

| Cita | PDF | Motivo del descarte |
|---|---|---|
| del Valle Martín, E.; de la Fuente Valentín, L. (2023). *Sentiment Analysis Methods for Politics and Hate Speech Contents in Spanish Language: A Systematic Review*. IEEE Latin America Transactions 21(3). | `pdfs/Irrelevantes/7268.pdf` | Revisión en español, pero centrada en discurso de odio; no aporta a AP ni a YouTube. |
| Qorib, M.; Cotae, P. (2026). *Hybrid Negation: Enhancing Sentiment Analysis for Complex Sentences*. Applied Sciences 16, 1000. | `pdfs/Irrelevantes/applsci-16-01000.pdf` | Mejora de negación en SA; fuera del alcance metodológico actual. |
| Xu, K. et al. (2022). *BiERU: Bidirectional emotional recurrent unit for conversational sentiment analysis*. Neurocomputing 467, 73–82. | `pdfs/Irrelevantes/BiERU.pdf` | Arquitectura para conversaciones; no aplicable al corpus actual. |
| Montufar Mercado, R. N.; Chacca Chuctaya, H. F.; Castro Gutierrez, E. G. (2018). *Automatic Cyberbullying Detection in Spanish-language Social Networks using Sentiment Analysis Techniques*. IJACSA 9(7). | `pdfs/Irrelevantes/Paper_33-Automatic_Cyberbullying_Detection.pdf` | Ciberacoso, no polarización política. |
| Notas sueltas de `Aplicados.md` (TripAdvisor, AFP, e-commerce, reseñas, etc.) | `pdfs/Irrelevantes/Aplicados.md` | Dominios no políticos o sin datos públicos pertinentes; ver el archivo para el detalle. |
