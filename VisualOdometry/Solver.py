import numpy as np
import cv2
import math
from scipy import linalg
from Numerics import Lie, Utils, ImageProcessing, JacobianGenerator
from Numerics.Utils import matrix_data_type
from VisualOdometry import GradientStepManager
from VisualOdometry import GaussNewtonRoutines
from Visualization import Plot3D
import time



def solve_SE3(X, Y, max_its, eps):
    # init
    # array for twist values x, y, z, roll, pitch, yaw
    t_est = np.array([0, 0, 0], dtype=matrix_data_type).reshape((3, 1))
    R_est = np.array([[1, 0, 0],
                      [0, 1, 0],
                      [0, 0, 1]], dtype=matrix_data_type)
    I_3 = np.identity(3, dtype=matrix_data_type)
    (position_vector_size, N) = X.shape
    twist_size = 6
    stacked_obs_size = position_vector_size * N
    homogeneous_se3_padding = Utils.homogenous_for_SE3()
    L_mean = -1
    it = -1
    # Step Factor
    alpha = 0.125

    SE_3_est = np.append(np.append(R_est, t_est, axis=1), Utils.homogenous_for_SE3(), axis=0)

    generator_x = Lie.generator_x()
    generator_y = Lie.generator_y()
    generator_z = Lie.generator_z()
    generator_roll = Lie.generator_roll()
    generator_pitch = Lie.generator_pitch()
    generator_yaw = Lie.generator_yaw()

    for it in range(0, max_its, 1):
        # accumulators
        J_v = np.zeros((twist_size, 1))
        normal_matrix = np.zeros((twist_size, twist_size))

        Y_est = np.matmul(SE_3_est, X)
        v = Y_est - Y

        L = np.sum(np.square(v), axis=0)
        L_mean = np.mean(L)

        if L_mean < eps:
            print('done')
            break

        Js = JacobianGenerator.get_jacobians_lie(generator_x, generator_y, generator_z, generator_yaw, generator_pitch,
                                                 generator_roll, Y_est, N, stacked_obs_size, coefficient=2.0)

        for i in range(0, N, 1):
            J = Js[i]
            J_t = np.transpose(J)
            error_vector = np.reshape(v[:, i], (position_vector_size, 1))
            J_v += np.matmul(-J_t, error_vector)
            normal_matrix += np.matmul(J_t, J)

        ##########################################################

        # TODO: Investigate faster inversion with QR
        try:
            pseudo_inv = linalg.inv(normal_matrix)
            # (Q,R) = linalg.qr(normal_matrix_2)
        except:
            print('Cant invert')
            return SE_3_est
        w = np.matmul(pseudo_inv, J_v)
        # Apply Step Factor
        w = alpha*w

        w_transpose = np.transpose(w)
        w_x = Utils.skew_symmetric(w[3], w[4], w[5])
        w_x_squared = np.matmul(w_x, w_x)

        # closed form solution for exponential map
        theta = math.sqrt(np.matmul(w_transpose, w))
        theta_sqred = math.pow(theta, 2)
        # TODO use Taylor Expansion when theta_sqred is small
        try:
            A = math.sin(theta) / theta
            B = (1 - math.cos(theta)) / theta_sqred
            C = (1 - A) / theta_sqred
        except:
            print('bad theta')
            return SE_3_est

        u = np.array([w[0], w[1], w[2]]).reshape((3, 1))

        R_new = I_3 + np.multiply(A, w_x) + np.multiply(B, w_x_squared)
        V = I_3 + np.multiply(B, w_x) + np.multiply(C, w_x_squared)

        t_est += + np.matmul(V, u)
        R_est = np.matmul(R_new, R_est)

        SE_3_est = np.append(np.append(R_est, t_est, axis=1), homogeneous_se3_padding, axis=0)
        print('Runtime mean error:', L_mean)

    print('mean error:', L_mean, 'iteration: ', it)
    return SE_3_est


def solve_photometric(frame_reference, frame_target, max_its, eps, alpha_step, use_ndc = False, debug = False):
    # init
    # array for twist values x, y, z, roll, pitch, yaw
    t_est = np.array([0, 0, 0], dtype=matrix_data_type).reshape((3, 1))
    #R_est = np.array([[0.0, -1.0, 0],
    #                  [1.0, 0.0, 0],
    #                  [0, 0, 1]], dtype=matrix_data_type)
    R_est = np.identity(3, dtype=matrix_data_type)
    I_3 = np.identity(3, dtype=matrix_data_type)

    (height,width) = frame_target.pixel_image.shape
    N = height*width
    position_vector_size = 3
    twist_size = 6
    stacked_obs_size = position_vector_size * N
    homogeneous_se3_padding = Utils.homogenous_for_SE3()
    # Step Factor
    #alpha = 0.125
    Gradient_step_manager = GradientStepManager.GradientStepManager(alpha_start = alpha_step, alpha_min = -0.7, alpha_step = -0.01 , alpha_change_rate = 0, gradient_monitoring_window_start = 3, gradient_monitoring_window_size = 0)
    v_mean = -10000
    v_mean_abs = -10000
    it = -1
    std = math.sqrt(0.4)
    image_range_offset = 10
    #depth_factor = 1.0
    #depth_factor = 1000 # 0.001 # ZR300


    SE_3_est = np.append(np.append(R_est, t_est, axis=1), Utils.homogenous_for_SE3(), axis=0)
    SE_3_est_orig = np.append(np.append(R_est, t_est, axis=1), Utils.homogenous_for_SE3(), axis=0)
    SE_3_est_last_valid = np.append(np.append(R_est, t_est, axis=1), Utils.homogenous_for_SE3(), axis=0)

    generator_x = Lie.generator_x_3_4()
    generator_y = Lie.generator_y_3_4()
    generator_z = Lie.generator_z_3_4()
    generator_roll = Lie.generator_roll_3_4()
    generator_pitch = Lie.generator_pitch_3_4()
    generator_yaw = Lie.generator_yaw_3_4()

    X_back_projection = np.ones((4, N), Utils.matrix_data_type)
    X_back_projection_last_valid = np.ones((4, N), Utils.matrix_data_type)
    valid_measurements_reference = np.full(N,False)
    valid_measurements_last = np.full(N,False)
    valid_measurements_target = np.full(N,False)
    valid_measurements = valid_measurements_reference

    # Precompute back projection of pixels
    GaussNewtonRoutines.back_project_image(width,
                                       height,
                                       image_range_offset,
                                       frame_reference.camera,
                                       frame_reference.pixel_depth,
                                       X_back_projection,
                                       valid_measurements,
                                       use_ndc)

    if debug:
        Plot3D.save_projection_of_back_projected(height,width,frame_reference,X_back_projection)

    # Precompute the Jacobian of SE3 around the identity
    J_lie = JacobianGenerator.get_jacobians_lie(generator_x, generator_y, generator_z, generator_yaw,
                                                generator_pitch,
                                                generator_roll, X_back_projection, N, stacked_obs_size, coefficient=2.0)

    # Precompute the Jacobian of the projection function
    J_pi = JacobianGenerator.get_jacobian_camera_model(frame_reference.camera.intrinsic, X_back_projection)

    # count the number of true
    #valid_measurements_total = np.logical_and(valid_measurements_reference,valid_measurements_target)

    #number_of_valid_reference = np.sum(valid_measurements_reference)
    #number_of_valid_total = np.sum(valid_measurements_total)
    #number_of_valid_measurements = number_of_valid_reference

    for it in range(0, max_its, 1):
        start = time.time()
        # accumulators
        #TODO: investigate preallocate and clear in a for loop
        J_v = np.zeros((twist_size, 1))
        normal_matrix = np.zeros((twist_size, twist_size))

        # Warp with the current SE3 estimate
        Y_est = np.matmul(SE_3_est, X_back_projection)
        v = np.zeros((N,1),dtype=matrix_data_type,order='F')

        target_index_projections = frame_target.camera.apply_perspective_pipeline(Y_est)

        v_sum = GaussNewtonRoutines.compute_residual(width,
                                                 height,
                                                 target_index_projections,
                                                 valid_measurements,
                                                 frame_target.pixel_image,
                                                 frame_reference.pixel_image,
                                                 v,
                                                 image_range_offset)

        number_of_valid_measurements = np.sum(valid_measurements_reference)

        Gradient_step_manager.save_previous_mean_error(v_mean_abs,it)

        v_mean = v_sum / number_of_valid_measurements
        valid_pixel_ratio = number_of_valid_measurements/N
        #v_mean_abs = np.abs(v_mean)
        #v_mean_abs = v_mean

        # TODO put this in gradient step manager
        #if valid_pixel_ratio< 0.8:
        #    print('Too many pixels are marked invalid')
        #    Gradient_step_manager.current_alpha+=0.1
        #    SE_3_est = SE_3_est_last_valid
        #    valid_measurements = valid_measurements_last
        #else:
        #    SE_3_est_last_valid = SE_3_est
        #    valid_measurements_last = valid_measurements

        Gradient_step_manager.track_gradient(v_mean_abs,it)

        if v_mean < eps:
            print('done, mean error:', v_mean)
            break

        Gradient_step_manager.analyze_gradient_history(it)
        #Gradient_step_manager.analyze_gradient_history_instantly(v_mean_abs)

        # See Kerl et al. ensures error decreases ( For pyramid levels )
        #if(v_mean > Gradient_step_manager.last_error_mean_abs):
            #continue

        GaussNewtonRoutines.gauss_newton_step(width,
                                          height,
                                          valid_measurements,
                                          J_pi,
                                          J_lie,
                                          frame_target.grad_x,
                                          frame_target.grad_y,
                                          v,
                                          J_v,
                                          normal_matrix,
                                          image_range_offset)

        # TODO: Investigate faster inversion with QR
        try:
            pseudo_inv = linalg.inv(normal_matrix)
            #(Q,R) = linalg.qr(normal_matrix)
            #Q_t = np.transpose(Q)
            #R_inv = linalg.inv(R)
            #pseudo_inv = np.multiply(R_inv,Q_t)
        except:
            print('Cant invert')
            return SE_3_est

        w = np.matmul(pseudo_inv, J_v)
        # Apply Step Factor
        w = Gradient_step_manager.current_alpha*w

        w_transpose = np.transpose(w)
        w_x = Utils.skew_symmetric(w[3], w[4], w[5])
        w_x_squared = np.matmul(w_x, w_x)

        # closed form solution for exponential map
        theta = math.sqrt(np.matmul(w_transpose, w))
        theta_sqred = math.pow(theta, 2)
        # TODO use Taylor Expansion when theta_sqred is small
        try:
            A = math.sin(theta) / theta
            B = (1 - math.cos(theta)) / theta_sqred
            C = (1 - A) / theta_sqred
        except:
            print('bad theta')
            return SE_3_est

        u = np.array([w[0], w[1], w[2]]).reshape((3, 1))

        R_new = I_3 + np.multiply(A, w_x) + np.multiply(B, w_x_squared)
        V = I_3 + np.multiply(B, w_x) + np.multiply(C, w_x_squared)

        t_est += + np.matmul(V, u)
        R_est = np.matmul(R_new, R_est)

        SE_3_est = np.append(np.append(R_est, t_est, axis=1), homogeneous_se3_padding, axis=0)
        end = time.time()
        print('mean error:', v_mean, 'iteration: ', it,'valid pixel ratio: ',valid_pixel_ratio, 'runtime: ', end-start)

    return SE_3_est
