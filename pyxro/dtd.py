# -*- coding: utf-8 -*-
"""
Created on Fri Nov  8 14:01:41 2019

@author: Henrique
"""

import periodictable as pt
import numpy as np
import scipy as sp
import matplotlib.pyplot as plt
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen import Structure

class Sample(object):
    def __init__(self, filename, hkl, nuc=1, shift=0.0):
        # Load crystal structure and gets the symmetrized structure
        self.structure = Structure.from_file(filename)
        self.symstruct = SpacegroupAnalyzer(self.structure).get_symmetrized_structure()
        
        # Number of unit cells to consider
        self.number_of_ucs = nuc
        
        # Number attenuation factor
        self.att_factor = 0.0
        
        # Debye-Waller factor
        self.DWF = 0.0
        
        # Calculates interplanar distance
        self.hkl = np.array(hkl)
        self.d_hkl = self.structure.lattice.d_hkl(self.hkl)
        self.hkl_norm = self.hkl/np.sqrt(np.dot(self.hkl, self.hkl))
        self.z_dist = np.dot(self.hkl_norm, self.symstruct.lattice.abc)
    
        
        tmpa = np.random.randn(3)
        tmpa -= tmpa.dot(self.hkl_norm) * self.hkl_norm
        tmpa /= np.linalg.norm(tmpa)
        tmpb = np.cross(tmpa, self.hkl_norm)
        self.hkl_perp = (tmpa + tmpb)/np.linalg.norm(tmpa + tmpb)
        
        all_pos = []
        for idx, sites in enumerate(self.symstruct.equivalent_sites):
            all_pos = np.append(all_pos, np.array([np.dot(self.hkl_norm, S.coords) for S in sites]))

        # Sets sites
        self.sites = {}
        self.zpos = {}
        self.geom_factor = {}
        self.cohpos = {}
        self.cohfra = {}
        for idx, sites in enumerate(self.symstruct.equivalent_sites):
            self.sites[idx] = sites[0].specie.name + str(idx)
            self.zpos[idx] = np.array([np.dot(self.hkl_norm, S.coords) for S in sites])
            self.zpos[idx] -= all_pos.min()
            self.zpos[idx] -= shift*self.z_dist
            self.zpos[idx] %= self.z_dist
            self.geom_factor[idx] = np.sum([np.exp(2j*np.pi*z/self.d_hkl) for z in self.zpos[idx]])
            self.cohfra[idx] = np.abs(self.geom_factor[idx]) / len(sites)
            self.cohpos[idx] = np.remainder(np.angle(self.geom_factor[idx]) / (2*np.pi), 1)

        self.toplayer = None
        
    def wavelength_energy_relation(self, t):
        h  = sp.constants.value('Planck constant in eV s')
        c  = sp.constants.value('speed of light in vacuum')
        return h*c/(t*1e-10)
        
    def set_mode(self, mode = 'angular', angle=0.0, energy=0.0, polarization='sigma'):
        self.mode = mode
        self.polarization = polarization
        
        if mode == 'angular':
            if energy == 0.0:
                # implementar erro
                self.energy_Bragg = 3000
            else:
                self.energy_Bragg = energy

            self.lambda_Bragg = self.wavelength_energy_relation(self.energy_Bragg)
            self.theta_Bragg  = np.degrees(np.arcsin(self.lambda_Bragg/(2*self.d_hkl)))
        elif mode == 'energy':
            if angle == 0.0:
                self.energy_Bragg = energy
                self.lambda_Bragg = self.wavelength_energy_relation(self.energy_Bragg)
                self.theta_Bragg  = np.degrees(np.arcsin(self.lambda_Bragg/(2*self.d_hkl)))
            else:
                self.theta_Bragg = angle
                self.lambda_Bragg = 2*self.d_hkl*np.sin(np.radians(self.theta_Bragg))
                self.energy_Bragg = self.wavelength_energy_relation(self.lambda_Bragg)

        self.theta_Bragg_rad = np.radians(self.theta_Bragg)
    
    def calc_imfp(self):
        density = self.symstruct.density
        M_weight = self.symstruct.composition.weight
        E_g = 0.0
        N_V = 8.0
        E_kinetic = self.energy_Bragg
        E_p = 28.8 * np.sqrt((N_V * density) / M_weight)  
        beta = (-0.10 + (0.944 / (np.sqrt(E_p**2 + E_g**2))) + 
               (0.069 * (density**0.1))) 
        gamma = 0.191 * (1 / np.sqrt(density))
        C_func = 1.97 - (1.096E-3 * E_p**2)
        D_func = 53.4 - (0.025 * E_p**2)
        
        imfp = (E_kinetic / ((E_p**2) * ((beta * np.log(gamma * E_kinetic)) 
               - (C_func / E_kinetic) + (D_func / E_kinetic**2))))
        
        self.imfp = imfp
        
    def calc_susceptibility(self, energy):
        F_0  = 0
        F_H  = 0
        F_Hb = 0

        r0 = sp.constants.value('classical electron radius')
        gamma = 1e10*(r0*self.wavelength_energy_relation(energy)**2)/(np.pi*self.structure.volume)
    
        # Debye-Waller correction to F_H and FH_Hb: exp(-Bs²), with B = 8*pi*<u**2>, s = sin(th)/lambda = 1/(2*d_hkl)
        DW_correction = self.DWF/(2*self.d_hkl)**2
        
        for idx, _ in enumerate(self.structure.sites):
            site = self.structure.sites[idx]
            ptab = pt.elements[site.specie.number]
            
            f0 = ptab.xray.f0(1/(2*self.d_hkl))
            f1, f2 = ptab.xray.scattering_factors(energy=energy/1000)
            prefac = (f0 - site.specie.number + f1 + 1j*f2)
            
            F_0  += (f1 + 1j*f2)
            F_H  += prefac*np.exp(2j*np.pi*np.dot( self.hkl, site.frac_coords) - self.DWF)
            F_Hb += prefac*np.exp(2j*np.pi*np.dot(-self.hkl, site.frac_coords) - self.DWF)
        
        return gamma*F_0, gamma*F_H, gamma*F_Hb


    def calc_reflectivity(self, delta=10, dx=0, Mono=False):
        Chi_0, Chi_H, Chi_Hb = self.calc_susceptibility(self.energy_Bragg)
        
        if self.polarization == 'pi':
            P = 2*np.cos(np.radians(self.theta_Bragg))
        else:
            P = 1.0
            
        b = -1
        
        self.backscattering_angle = np.degrees(np.pi/2 - 2*np.abs(Chi_0))
        
        self.angle_offset = np.degrees(np.real(Chi_0)/np.sin(2*self.theta_Bragg_rad))
        self.angle_range  = np.degrees(np.abs(P)*np.sqrt(np.abs(Chi_H*Chi_Hb))/np.sin(2*self.theta_Bragg_rad))
        self.energy_offset = np.real(Chi_0)*self.energy_Bragg/(2*np.sin(self.theta_Bragg_rad)**2)
        self.energy_range  = self.energy_Bragg*np.abs(P)*np.sqrt(np.abs(Chi_H*Chi_Hb))/(2*np.sin(self.theta_Bragg_rad)**2)
        
        if self.mode == 'angular':
            if dx == 0:
                dx = 0.001
            npts = int(2*delta/dx)+1
            x_range = np.linspace(-delta, delta, npts)
            
            xarg = np.radians(x_range)
            targ = np.radians(self.theta_Bragg)
            if self.theta_Bragg < self.backscattering_angle:
                first_term = b*xarg*np.sin(2*targ)
            else:
                first_term = np.sqrt(1 + 2*xarg**2 * (np.sin(targ))**2 + 2*b*xarg*np.sin(2*targ)) - 1
        elif self.mode == 'energy':
            if dx == 0:
                dx = 0.01
            npts = int(2*delta/dx)+1
            x_range = np.linspace(-delta, delta, npts)
            
            xarg = x_range/(x_range + self.energy_Bragg)
            targ = np.radians(self.theta_Bragg)
            first_term = 2*b*xarg*(np.sin(targ))**2
             
        eta = (first_term + ((1-b)/2)*Chi_0) / (np.absolute(P)*np.sqrt(np.absolute(b)*Chi_H*Chi_Hb))
    
        prefactor = np.sqrt(np.abs(b)) * (np.abs(P)/P) * np.sqrt(Chi_H/Chi_Hb)
        EHE0 = -prefactor*np.piecewise(eta, np.real(eta) > 0,
                 [lambda x: x-(x**2-1)**.5, lambda x: x+(x**2-1)**.5])
        
        Refl = np.abs(EHE0)**2
        Phase = np.remainder(np.angle(EHE0) + np.pi/2, 2*np.pi) - np.pi/2

        self.x_range = x_range
        self.Refl = Refl
        self.Phase = Phase
        self.Mono = Mono
        
        if self.Mono:
            self.Mono.set_mode(self.mode, energy=self.energy_Bragg)
            self.Mono.calc_reflectivity(delta=delta, dx=dx)
            
            shift_sample = (self.angle_offset if self.mode == 'angular' else self.energy_offset)
            shift_mono = (self.Mono.angle_offset if self.mode == 'angular' else self.Mono.energy_offset)

            self.Refl_shifted = np.interp(self.x_range, self.x_range - shift_sample, self.Refl)
            self.Phase_shifted = np.interp(self.x_range, self.x_range - shift_sample, self.Phase)
            self.Mono.Refl_shifted = np.interp(self.Mono.x_range, self.Mono.x_range - shift_mono, self.Mono.Refl)
            
            self.Mono.Squared_Refl = self.Mono.Refl_shifted**2/np.sum(self.Mono.Refl_shifted**2)
            self.Refl_conv_Mono = np.correlate(self.Refl, self.Mono.Squared_Refl, mode='same')
            self.Phase_conv_Mono = np.correlate(self.Phase, self.Mono.Squared_Refl, mode='same')
    
    def calc_sw_cohpos(self, CF, CP, Q = 0.0, Delta = 0.0):
        if self.Mono:
            R = self.Refl_conv_Mono
            P = self.Phase_conv_Mono
        else:
            R = self.Refl
            P = self.Phase
            
        S_R = (1 + Q)/(1 - Q)
        S_I = np.sqrt(1 + (Q*np.tan(np.radians(Delta)))**2)/(1 - Q)
        Psi = np.arctan(Q*np.tan(np.radians(Delta)))
        
        return 1 + S_R*R + 2*np.abs(S_I)*np.sqrt(R)*CF*np.cos(P - 2*np.pi*CP + Psi)
    
    def calc_yield(self):
        self.calc_imfp()
        lambda_IMFP = self.imfp * np.sin(np.radians(self.theta_Bragg))

        Y = {}
        for idx, sites in enumerate(self.symstruct.equivalent_sites):
            tmpY = self.calc_sw_cohpos(self.cohfra[idx], self.cohpos[idx])
            Y[idx] = np.zeros((len(tmpY), self.number_of_ucs))
            for uc in np.arange(self.number_of_ucs):
                Y[idx][:, uc] = tmpY * np.exp(-uc*self.z_dist/lambda_IMFP)
            Y[idx] = Y[idx].sum(axis=1)/self.number_of_ucs
        self.Y = Y
        
        if self.toplayer != None:
            self.toplayer.Y = {}
            uniq_cohpos, uniq_idx = np.unique(list(self.toplayer.cohpos.values()), return_index=True)
            for idx in uniq_idx:
                name = self.toplayer.structure.sites[idx].specie.name + str(idx)
                self.toplayer.Y[name] = self.calc_sw_cohpos(self.toplayer.cohfra[idx], self.toplayer.cohpos[idx])


    def calc_electric_field(self, npts=501):
        z_min = 0.0
        if self.toplayer != None:
            all_pos = []
            for idx, site in self.toplayer.sites.items():
                all_pos = np.append(all_pos, self.toplayer.zpos[idx])
            z_min = all_pos.max()

        z_range = np.linspace(z_min, -self.number_of_ucs*self.z_dist, npts)
        self.ElectricField = np.zeros((len(z_range), len(self.x_range)))
        
        for idx, z in enumerate(z_range):
            geom_factor = np.exp(2j*np.pi*z/self.d_hkl)
            coh_position = np.remainder(np.angle(geom_factor) / (2*np.pi), 1)
            self.ElectricField[idx, :] = np.exp(-self.att_factor*z)*self.calc_sw_cohpos(1.0, coh_position)
            
        self.z_range = z_range
        
    def set_toplayer(self, toplayer, distance):
        self.toplayer = toplayer
        self.toplayer.distance = distance
        self.toplayer.sites = {}
        self.toplayer.zpos = {}
        self.toplayer.geom_factor = {}
        self.toplayer.cohpos = {}
        self.toplayer.cohfra = {}
        
        all_pos = []
        for idx, site in enumerate(self.toplayer.structure.sites):
            all_pos = np.append(all_pos, np.dot(self.toplayer.hkl_norm, site.coords))
            
        for idx, site in enumerate(self.toplayer.structure.sites):
            self.toplayer.sites[idx] = site.specie.name + str(idx)
            self.toplayer.zpos[idx] = np.dot(self.toplayer.hkl_norm, site.coords) 
            self.toplayer.zpos[idx] -= all_pos.min()
            self.toplayer.zpos[idx] += self.toplayer.distance
            self.toplayer.geom_factor[idx] = np.exp(2j*np.pi*self.toplayer.zpos[idx]/self.d_hkl)
            self.toplayer.cohfra[idx] = np.abs(self.toplayer.geom_factor[idx])
            self.toplayer.cohpos[idx] = np.remainder(np.angle(self.toplayer.geom_factor[idx]) / (2*np.pi), 1)
    
    def print(self):
        if self.toplayer:
            print('Top layer:')
            for idx, site in self.toplayer.sites.items():
                print('{:>3}: {:>6.3f} {:>4.2}'.format(site, self.toplayer.zpos[idx], self.toplayer.cohpos[idx]))
        
        print('Sample/substrate:')
        for idx, equivsite in self.sites.items():
            for sitez in self.zpos[idx]:
                print('{:>2}: {:>6.3f} {:>4.2}'.format(equivsite, sitez, self.cohpos[idx]))
        

def plot_Refl_and_Phase(Sample, colors=None, trim=0, mode='relative'):
    f, (ax1, ax3) = plt.subplots(2, 1, sharex=True, figsize=(4.5,6))
    ax2 = ax1.twinx()
    
    ax1.set_ylabel('Reflectivity')
    ax2.set_ylabel(r'Phase ($\pi$)')
    
    if Sample.mode == 'energy':
        if mode == 'relative':
            ax3.set_xlabel('Relative photon energy (eV)')
        else:
            ax3.set_xlabel('Photon energy (eV)')
        plt.title('E$_B$ = {:.2f} eV @ {:.2f} deg'.format(Sample.energy_Bragg, Sample.theta_Bragg))
    elif Sample.mode == 'angular':
        if mode == 'relative':
            ax3.set_xlabel(r'Relative incident angle ($\degree$)')
        else:
            ax3.set_xlabel(r'Incident angle ($\degree$)')
        plt.title(r'$\theta_B$ = {:.2f}$\degree$ @ {:.2f} eV'.format(Sample.theta_Bragg, Sample.energy_Bragg))
        
    ax3.set_ylabel('Photoemission yield')
    
    ax1.tick_params(which='both', axis='both', direction='in', top=True, left=True)
    ax2.tick_params(which='both', axis='both', direction='in')
    ax3.tick_params(which='both', axis='both', direction='in', top=True, left=True, right=True)
    
    ax1.minorticks_on()
    ax2.minorticks_on()
    ax3.minorticks_on()
    
    if mode == 'absolute':
        if Sample.mode == 'energy':
            xshift = Sample.energy_Bragg
        elif Sample.mode == 'angular':
            xshift = Sample.theta_Bragg
    elif mode == 'relative':
        xshift = 0.0
        
    l_r = ax1.plot(Sample.x_range + xshift, Sample.Refl, c='b', label='R (sample)')
    l_p = ax2.plot(Sample.x_range + xshift, Sample.Phase/np.pi, c='g', label='Phase')
    lns = l_p + l_r
    
    if Sample.Mono:
        l_m = ax1.plot(Sample.x_range + xshift, Sample.Mono.Refl, c='r', label='R (mono)')
        l_rc = ax1.plot(Sample.x_range + xshift, Sample.Refl_conv_Mono, c='k', label='R (conv)')
        l_pc = ax2.plot(Sample.x_range + xshift, Sample.Phase_conv_Mono/np.pi, c='y', label='P (conv)')
        lns += l_rc + l_pc + l_m
    

    if Sample.toplayer != None:
        for idx, y in Sample.toplayer.Y.items():
            y += 1 - y.mean()
            ax3.plot(Sample.x_range + xshift, y, label=idx, c='r')
        
    for idx, sites in enumerate(Sample.symstruct.equivalent_sites):
        if colors:
            clr = colors[Sample.symstruct.equivalent_sites[idx][0].specie.name]
        else:
            clr = 'b'
        element = Sample.symstruct.sites[Sample.symstruct.equivalent_indices[idx][0]].species_string
        y = Sample.Y[idx]
        y += 1 - y.mean()
        ax3.plot(Sample.x_range + xshift, y, label=element, c=clr)
        
    lbl = [l.get_label() for l in lns]
    ax1.legend(lns, lbl)
    ax3.legend()
    
    plt.xlim(Sample.x_range[0] + trim + xshift, Sample.x_range[-1] - trim + xshift)
    
    plt.locator_params(axis='x', integer=True)
    
    plt.tight_layout()
    plt.subplots_adjust(hspace=0.0)
    plt.show()

def plot_Electric_Field(Sample, trim=0, colors=None):
    f, ax = plt.subplots(1, 2, sharex=True, figsize=(4,5), gridspec_kw=dict(width_ratios=[3, 1]))
    
    ax[0].minorticks_on()
    ax[0].tick_params(which='both', axis='y', direction='in', labelleft=True, left=True)
    ax[1].tick_params(which='both', axis='both', labelleft=False, left=False, right=True, labelright=True, direction='in')
    
    # Plots electric field
    ax[0].pcolormesh(Sample.x_range, Sample.z_range, Sample.ElectricField)

    # Plots top layer
    if Sample.toplayer:
        ax[0].axhline(y=Sample.toplayer.distance, c='k')
        ax[0].text(0, Sample.toplayer.distance/2, '{:.3f}'.format(Sample.toplayer.distance), ha='center', va='center')
        ax[0].axhline(y=0, c='k')

        for idx, site in Sample.toplayer.sites.items():
            if colors:
                clr = colors[Sample.toplayer.structure.sites[idx].specie.name]
            else:
                clr = 'b'
            ax[0].scatter(0, Sample.toplayer.zpos[idx], c=clr, s=50)
            SW = Sample.calc_sw_cohpos(1.0, Sample.toplayer.cohpos[idx])
            SW -= SW.mean()
            SW /= 3
            ax[1].plot(Sample.x_range, SW + Sample.toplayer.zpos[idx]/Sample.d_hkl, c=clr)

    # Plots main structure / substrate
    for idx, equivsite in Sample.sites.items():
        if colors:
            clr = colors[Sample.symstruct.equivalent_sites[idx][0].specie.name]
        else:
            clr = 'b'
            
        for sitez in Sample.zpos[idx]:
            x_list = np.array([0 for n in np.arange(Sample.number_of_ucs+1)])
            y_list = -np.array([sitez + n*Sample.z_dist for n in np.arange(Sample.number_of_ucs+1)])
            ax[0].scatter(x_list, y_list, c=clr, s=50)
            for i,z in enumerate(y_list):
                SW = Sample.calc_sw_cohpos(1.0, Sample.cohpos[idx])
                SW -= SW.mean()
                SW /= 3
                ax[1].plot(Sample.x_range, SW + z/Sample.d_hkl, c=clr)

    if Sample.mode == 'energy':
        ax[0].set_xlabel(r'Relative photon energy (eV)')
        ax[0].set_title('E$_B$ = {:.2f} eV @ {:.2f}$\degree$'.format(Sample.energy_Bragg, Sample.theta_Bragg))
    elif Sample.mode == 'angular':
        ax[0].set_xlabel(r'Relative incident angle ($\degree$)')
        ax[0].set_title(r'$\theta_B$ = {:.2f}$\degree$ @ {:.2f} eV'.format(Sample.theta_Bragg, Sample.energy_Bragg))

    ax[0].set_ylabel('Depth ($\AA$)')
    ax[0].set_xlim(Sample.x_range[0] + trim, Sample.x_range[-1] - trim)
    ax[0].set_ylim(Sample.z_range.min(), Sample.z_range.max() + Sample.d_hkl)
    ax[1].set_ylim(Sample.z_range.min()/Sample.d_hkl, (Sample.z_range.max() + Sample.d_hkl)/Sample.d_hkl)
    plt.tight_layout()
    plt.subplots_adjust(wspace=0.0)
    plt.show()