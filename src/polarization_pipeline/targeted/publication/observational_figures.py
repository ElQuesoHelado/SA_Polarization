"""Publication-size English figures derived from immutable aggregate reports."""
from pathlib import Path

import numpy as np
import pandas as pd

from .state import verify_seal

GROUPS = ('izquierda', 'derecha')
NAMES = ('Left', 'Right')
VARIANTS = ('Reversed A/B', 'Video-balanced', 'Without Keiko Fujimori',
            'Without Roberto Sánchez', 'Without Rafael López Aliaga', 'Historical data only')


def render_frames(destination, primary, intervals, sensitivities, *, prefix=''):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    created = []
    def save(fig, name):
        if fig.get_layout_engine() is None:
            fig.tight_layout(pad=.6)
        for extension in ('pdf', 'png'):
            path = destination / (prefix + name + '.' + extension)
            fig.savefig(path, dpi=220)
            created.append(path)
        plt.close(fig)
    # A 3.4-inch figure is placed at a full IEEE column: no panel shrinking.
    with plt.rc_context({'font.size':9, 'axes.labelsize':9, 'xtick.labelsize':8.5,
                         'ytick.labelsize':8.5, 'legend.fontsize':8.5, 'pdf.fonttype':42}):
        fig,ax=plt.subplots(figsize=(3.4,2.65))
        ax.hist(primary.gap,bins=np.linspace(-2,2,21),color='#3974a8',edgecolor='white')
        ax.axvline(primary.gap.mean(),color='#b33b2e',label='Mean')
        ax.axvline(primary.gap.median(),color='black',linestyle='--',label='Median')
        ax.set(xlabel='Normalized gap',ylabel='Users',xlim=(-2.1,2.1))
        ax.legend(loc='upper left');save(fig,'gap_distribution')
        fig,ax=plt.subplots(figsize=(3.4,2.65))
        ax.boxplot([primary.N_in,primary.N_out],tick_labels=['Own bloc','Opposing bloc'],showfliers=True)
        ax.set(ylabel='Evaluable events in B',yscale='log')
        save(fig,'event_support')
        frame=intervals.set_index('metric')
        matrix=np.array([[frame.loc['balance_'+g+'_'+t,'estimate'] for t in GROUPS] for g in GROUPS])
        fig,ax=plt.subplots(figsize=(3.5,3.0),layout='constrained')
        im=ax.imshow(matrix,vmin=-1,vmax=1,cmap='RdBu')
        ax.set(xticks=[0,1],xticklabels=NAMES,yticks=[0,1],yticklabels=NAMES,
               xlabel='Target political bloc',ylabel='Observed political affinity')
        for i,g in enumerate(GROUPS):
            for j,t in enumerate(GROUPS):
                r=frame.loc['balance_'+g+'_'+t]
                bounds=f'[{r.ci_low:.3f}, {r.ci_high:.3f}]'.replace('0.','.')
                label=f'{r.estimate:.3f}\n{bounds}'
                ax.text(j,i,label,ha='center',va='center',fontsize=8.5,
                        color='white' if abs(r.estimate)>.65 else 'black')
        fig.colorbar(im,ax=ax,label='Normalized balance',fraction=.055,pad=.04)
        save(fig,'balance_matrix')
        # This wider figure is intended for a two-column/supplement placement.
        fig,ax=plt.subplots(figsize=(7,3.45))
        variants=sensitivities.iloc[:6]
        for i,r in enumerate(variants.itertuples()):
            if np.isfinite(r.ci_low):ax.plot([r.ci_low,r.ci_high],[i,i],color='#3974a8')
            ax.plot(r.gap,i,'o',color='#3974a8')
            ax.text(2.05,i,f'n={r.users}',va='center',fontsize=9)
        ax.axvline(0,color='gray',linestyle='--')
        ax.set(yticks=np.arange(len(variants)),yticklabels=VARIANTS,
               xlabel='Normalized gap and 95% CI',xlim=(-.05,2.4))
        ax.invert_yaxis();save(fig,'sensitivities')
    return created


def export(report, destination):
    """Never rewrite the sealed analysis, even when only labels would change."""
    report,destination=Path(report),Path(destination)
    if destination.resolve().is_relative_to(report.resolve()):
        raise ValueError('Presentation exports must remain outside the sealed report')
    verify_seal(report)
    return render_frames(destination,pd.read_csv(report/'user_scores.csv'),
        pd.read_csv(report/'intervals.csv'),pd.read_csv(report/'sensitivities.csv'),
        prefix='observational_')
