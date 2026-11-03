"""Fetch a subset of Google's Willow 105Q surface-code data (Zenodo 13273331, CC-BY-4.0) via HTTP range requests."""
import os
from remotezip import RemoteZip
U='https://zenodo.org/api/records/13273331/files/google_105Q_surface_code_d3_d5_d7.zip/content'
P='google_105Q_surface_code_d3_d5_d7/'
EXPS=[f'{p}/{b}/{r}' for p in ['d7_at_q6_7','d5_at_q6_5','d3_at_q6_7'] for b in 'XZ' for r in ['r10','r30']]
F=['detection_events.b8','obs_flips_actual.b8','metadata.json','circuit_noisy_si1000.stim',
   'decoding_results/correlated_matching_decoder_with_rl_optimized_prior/error_model.dem',
   'decoding_results/correlated_matching_decoder_with_si1000_prior/error_model.dem']
if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    z=RemoteZip(U)
    for e in EXPS:
        for f in F:
            if not os.path.exists(f'data/willow/{P}{e}/{f}'): z.extract(P+e+'/'+f,'data/willow')
        print('ok',e,flush=True)
