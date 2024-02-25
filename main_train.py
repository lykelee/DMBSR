import os
import os.path
import math
import argparse
import time
import random
import numpy as np
from collections import OrderedDict
import logging
from torch.utils.data import DataLoader
import torch

from utils import utils_logger
from utils import utils_image as util
from utils import utils_option as option
from utils import utils_sisr as sisr
from utils import utils_dist as dist

from data.select_dataset import define_Dataset
from models.select_model import define_Model


def main(json_path="options/train_mbsr.json"):
    """
    # ----------------------------------------
    # Step--1 (prepare opt)
    # ----------------------------------------
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-opt", type=str, default=json_path, help="Path to option JSON file."
    )
    parser.add_argument("--local_rank", type=int, default=0)  # added GC
    opt = option.parse(parser.parse_args().opt, is_train=True)
    util.mkdirs((path for key, path in opt["path"].items() if "pretrained" not in key))

    current_step = opt["train"]["current_step"] if opt["train"]["current_step"] else 0
    border = opt["scale"]
    # dist.init_dist("pytorch")  # GC
    # ----------------------------------------
    # save opt to  a '../option.json' file
    # ----------------------------------------
    option.save(opt)

    # ----------------------------------------
    # return None for missing key
    # ----------------------------------------
    opt = option.dict_to_nonedict(opt)

    # ----------------------------------------
    # configure logger
    # ----------------------------------------
    logger_name = "train"
    utils_logger.logger_info(
        logger_name, os.path.join(opt["path"]["log"], logger_name + ".log")
    )
    logger = logging.getLogger(logger_name)
    logger.info(option.dict2str(opt))

    # ----------------------------------------
    # seed
    # ----------------------------------------
    seed = opt["train"]["manual_seed"]
    if seed is None:
        seed = random.randint(1, 10000)
    logger.info("Random seed: {}".format(seed))
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    """
    # ----------------------------------------
    # Step--2 (creat dataloader)
    # ----------------------------------------
    """

    # ----------------------------------------
    # 1) create_dataset
    # 2) creat_dataloader for train and test
    # ----------------------------------------
    for phase, dataset_opt in opt["datasets"].items():
        if phase == "train":
            train_set = define_Dataset(dataset_opt)
            train_size = int(
                math.ceil(len(train_set) / dataset_opt["dataloader_batch_size"])
            )
            logger.info(
                "Number of train images: {:,d}, iters: {:,d}".format(
                    len(train_set), train_size
                )
            )
            train_loader = DataLoader(
                train_set,
                batch_size=dataset_opt["dataloader_batch_size"],
                shuffle=dataset_opt["dataloader_shuffle"],
                num_workers=dataset_opt["dataloader_num_workers"],
                drop_last=True,
                pin_memory=True,
            )
        elif phase == "test":
            test_set = define_Dataset(dataset_opt)
            test_loader = DataLoader(
                test_set,
                batch_size=1,
                shuffle=False,
                num_workers=1,
                drop_last=False,
                pin_memory=True,
            )
        else:
            raise NotImplementedError("Phase [%s] is not recognized." % phase)

    """
    # ----------------------------------------
    # Step--3 (initialize model)
    # ----------------------------------------
    """

    model = define_Model(opt)

    logger.info(model.info_network())
    model.init_train()
    logger.info(model.info_params())

    """
    # ----------------------------------------
    # Step--4 (main training)
    # ----------------------------------------
    """

    for epoch in range(opt["train"]["n_epochs"]):  # keep running
        for i, train_data in enumerate(train_loader):
            current_step += 1
            # print('current step = %d' % i)

            # -------------------------------
            # 1) update learning rate
            # -------------------------------
            model.update_learning_rate(current_step)

            # -------------------------------
            # 2) feed patch pairs
            # -------------------------------
            model.feed_data(train_data)

            # -------------------------------
            # 3) optimize parameters
            # -------------------------------
            model.optimize_parameters(current_step)

            # -------------------------------
            # 4) training information
            # -------------------------------
            if current_step % opt["train"]["checkpoint_print"] == 0:
                logs = model.current_log()  # such as loss
                message = "<epoch:{:3d}, iter:{:8,d}, lr:{:.3e}> ".format(
                    epoch, current_step, model.current_learning_rate()
                )
                for k, v in logs.items():  # merge log information into message
                    message += "{:s}: {:.3e} ".format(k, v)
                logger.info(message)

            # -------------------------------
            # 5) save model
            # -------------------------------
            if current_step % opt["train"]["checkpoint_save"] == 0:
                logger.info("Saving the model.")
                model.save(current_step)

            # -------------------------------
            # 6) testing
            # -------------------------------
            if current_step % opt["train"]["checkpoint_test"] == 0:

                avg_psnr = 0.0
                idx = 0

                for test_data in test_loader:
                    idx += 1
                    image_name_ext = os.path.basename(test_data["L_path"][0])
                    img_name, ext = os.path.splitext(image_name_ext)

                    img_dir = os.path.join(opt["path"]["images"], img_name)
                    util.mkdir(img_dir)

                    model.feed_data(test_data)
                    model.test()

                    visuals = model.current_visuals()
                    E_img = util.tensor2uint(visuals["E"])
                    H_img = util.tensor2uint(visuals["H"])
                    L_img = util.tensor2uint(visuals["L"])

                    # -----------------------
                    # save images
                    # -----------------------
                    save_img_path = os.path.join(
                        img_dir, "{:s}_{:d}.png".format(img_name, current_step)
                    )
                    util.imsave(E_img, save_img_path)
                    util.imsave(H_img, save_img_path[:-4] + "_H.png")
                    util.imsave(L_img, save_img_path[:-4] + "_L.png")

                    if "fig" in visuals.keys():
                        fig = visuals["fig"]
                        fig.savefig(save_img_path[:-4] + "_pos.png")
                        util.imsave(
                            visuals["kernels_gt"],
                            save_img_path[:-4] + "_kernels_gt.png",
                        )
                        util.imsave(
                            visuals["kernels_estimated"],
                            save_img_path[:-4] + "_kernels_estimated.png",
                        )

                    if "kernels_grid" in visuals.keys():
                        util.imsave(
                            visuals["gt_kernels_grid"],
                            save_img_path[:-4] + "_kernels_gt.png",
                        )
                        util.imsave(
                            visuals["kernels_grid"],
                            save_img_path[:-4] + "_kernels_estimated.png",
                        )

                    # -----------------------
                    # calculate PSNR
                    # -----------------------
                    current_psnr = util.calculate_psnr(E_img, H_img, border=border)

                    logger.info(
                        "{:->4d}--> {:>10s} | {:<4.2f}dB".format(
                            idx, image_name_ext, current_psnr
                        )
                    )

                    avg_psnr += current_psnr

                avg_psnr = avg_psnr / idx

                # testing log
                logger.info(
                    "<epoch:{:3d}, iter:{:8,d}, Average PSNR : {:<.2f}dB\n".format(
                        epoch, current_step, avg_psnr
                    )
                )

    logger.info("Saving the final model.")
    model.save("latest")
    logger.info("End of training.")


if __name__ == "__main__":
    main()
