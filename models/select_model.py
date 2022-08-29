
"""
# --------------------------------------------
# define training model
# --------------------------------------------
"""


def define_Model(opt):
    model = opt['model']      # one input: L

    if model == 'plain':
        from models.model_plain import ModelPlain as M

    elif model == 'plain2':  # two inputs: L, C
        from models.model_plain2 import ModelPlain2 as M

    elif model == 'plain4':  # four inputs: L, k, sf, sigma
        from models.model_plain4 import ModelPlain4 as M
    
    elif model == 'multiblur':  # four inputs: L, kmap, basis, sf, sigma
        from models.model_multiblur import ModelMultiblur as M

    elif model == 'multiblur_gan':  # four inputs: L, kmap, basis, sf, sigma
        from models.model_gan_multiblur import ModelGAN as M
    elif model == 'pmpb':  # four inputs: L, positions, intrinsics, sf, sigma
        from models.model_pmpb import ModelPMPB as M
    elif model == 'blind_pmpb':  # four inputs: L, positions, intrinsics, sf, sigma
        from models.model_blind_pmpb import ModelBlindPMPB as M
    elif model == 'blind_nimbusr':  # four inputs: L, positions, intrinsics, sf, sigma
        from models.model_blind_nimbusr import ModelBlindNIMBUSR as M
    else:
        raise NotImplementedError('Model [{:s}] is not defined.'.format(model))

    m = M(opt)

    print('Training model [{:s}] is created.'.format(m.__class__.__name__))
    return m
