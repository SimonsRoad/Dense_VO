import numpy as np
import sys
from math import sqrt
import Numerics.Utils as Utils

t_min = 0.001

t_max = 500

def point_for_ray(ray, t):
    return ray.origin + np.multiply(t,ray.direction)

def generate_spheres(points : np.ndarray):
    (dim,N) = points.shape
    spheres = []
    for i in range(0,N):
        center = np.array(points[0:3,i]).reshape(3,1)
        spheres.append(Sphere(center,1.0))

    return spheres

class Ray:
    def __init__(self,origin : np.ndarray ,direction : np.ndarray):
        if origin.shape != (3,1):
            raise TypeError('Ray origin not shape (3,1)')
        self.origin = origin
        self.direction = direction

class Sphere:
    def __init__(self,origin : np.ndarray,radius : float):
        if origin.shape != (3,1):
            raise TypeError('Sphere origin not shape (3,1)')
        self.origin = origin
        self.radius = radius

    def intersections(self,ray : Ray ):
        center_to_ray = ray.origin - self.origin
        # A is always 1 since vectors are normalized
        B = 2.0 * Utils.fast_dot(center_to_ray, ray.direction)
        center_to_ray_dot = Utils.fast_dot(center_to_ray, center_to_ray)
        C = center_to_ray_dot - self.radius**2.0
        discriminant = (B**2.0) - 4.0*C
        if discriminant < 0:
            return (False,0,0)
        elif round(discriminant,3) == 0:
            return False, -B / 2.0 , sys.float_info.min
        else:
            return True, (-B + sqrt(discriminant))/2.0, (-B - sqrt(discriminant))/2.0

    def intersect(self, ray : Ray):
        (hasIntersection, i1, i2) = self.intersections(ray)
        if i1 >= t_min and i2 >= t_min:
            return hasIntersection, min(i1, i2)
        elif i1 < 0.0:
            return hasIntersection, i2
        else:
            return hasIntersection, i1

    def is_intersection_acceptable(self,b,t):
        return b and t > t_min

    def normal_for_point(self,point_on_shpere):
        return Utils.normalize(point_on_shpere - self.origin)


empty_sphere = Sphere(np.array([[0],[0],[0]]),1.0)



