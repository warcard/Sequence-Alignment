import numpy as np
import qutip as qu
import scipy.signal
import matplotlib.pyplot as plt
import types

def bit_arr_to_int(pattern):
    return np.sum(pattern*np.power(2, np.arange(len(pattern)-1, -1, -1)))

def str_to_bit_arr(bit_str):
    return np.array([x == "1" for x in bit_str])

def find_closest_int(func, iter_limit=100, scheme="ezhov"):
    start,point = func(0),func(1)
    increase = point - start
    limit = int(np.floor((iter_limit - start)/increase))
    while func(limit) < 2:
        limit += 1
    nums = np.arange(0, limit+1)
    print("iter_limit", iter_limit)
    print("limit=", limit)
    print("nums = ", nums)
    vals = func(nums)
    print("vals = ", vals)
    vals = np.abs(np.mod(vals, 1) - 0.5)
    alph = np.argmax(vals)
    M = int(np.round(func(nums[alph])))
    if scheme != "ezhov" and M < 2:
        M = 2
    print("M=",M)
    return M

def find_closest_peak(func, limit=10):
    vals = func(np.arange(limit))
    vals = np.abs(np.mod(vals, 1) - 0.5)
    plt.plot(vals)
    plt.show()
    peaks,_ = scipy.signal.find_peaks(vals)
    alph = peaks[0]
    print("found peak", alph, func(alph))
    return int(np.round(func(alph)))

def hamm_bin(center, *params):
    a = params[0]
    def hamm_dist(pattern, ref):
        return np.sum(np.logical_not(np.logical_xor(pattern, ref)))
    N = len(center)
    perm_numbers = np.arange(2**N-1, -1, -1)
    perms = [format(s, "0" + str(N) + "b") for s in range(len(perm_numbers))]
    perms = np.array([np.array([x == "1" for x in s]) for s in perms])
    weights = np.zeros(len(perms))
    for i in range(len(perms)):
        dist = hamm_dist(perms[i], center)
        weights[i] = np.sqrt((a**dist)*(1-a)**(N-dist))
    for i in range(len(perms)):
        if i == 0:
            state = weights[i]*qu.basis(len(perm_numbers), perm_numbers[i])
        else:
            state += weights[i]*qu.basis(len(perm_numbers), perm_numbers[i])
    return state.unit()

def excl_mem(pattern, state):
    N = 2**len(pattern)
    if state is None:
        state = sum([qu.basis(N, i) for i in range(N)])
        state = state.unit()
    pattern_state = qu.basis(N, bit_arr_to_int(pattern))
    state -= pattern_state.overlap(state)*pattern_state
    return state

def incl_mem(pattern, state):
    N = 2**len(pattern)
    if state is None:
        state = qu.Qobj()
    state += qu.basis(N, bit_arr_to_int(pattern))
    return state

class QuAM:

    def __init__(self):
        self.diffusion = None
        self.oracle = None
        self.mem_op = None
        self.query = None
        self.patterns = None
        self.memory = None
        self.memories = None
        self.state = None
        self.max_iterations = 1000

    def set_query(self, patterns, weights=None, scheme=None, bin_param=0.25):
        """Sets the pattern of the search

        Unless weights or different scheme is given, uses a Hamming distance binomial distribution for the distributed pattern query

        patterns - list of binary array for the patterns sought after : list of bool array
        weights - (relative) probability weights for the patterns in the query : numpy array of floats
        scheme - Function for making query distribution : function handle with 1 argument, the pattern
        """
        if weights is None:
            if scheme is None:
                scheme = lambda pattern: hamm_bin(pattern, bin_param)
            state = qu.Qobj()
            for pattern in patterns:
                state += scheme(str_to_bit_arr(pattern))
        else:
            state = qu.Qobj()
            max_ID = 2**len(patterns[0])
            for (pattern, weight) in zip(patterns, weights):
                state_id = bit_arr_to_int(str_to_bit_arr(pattern))
                state += weight*qu.basis(max_ID, state_id)
        state = state.unit()
        self.query = state
        self.patterns = patterns

    def set_mem(self, memories, scheme=None):
        """Sets the memory of the search

        Takes a list of states to remember, and a scheme of how to input them into the memory (standards: 'inclusion', 'exclusion', 'vary_phase')

        memories - list of binary arrays to memorize : list of bool numpy arrays
        scheme - the memorization scheme (standard: exclusion) : string or function handle taking a pattern and current memory state
        """
        if not scheme:
            scheme = "exclusion"
        if isinstance(scheme, str):
            if scheme == "inclusion":
                scheme = incl_mem
            elif scheme == "exclusion":
                scheme = excl_mem
            elif scheme == "vary_phase":
                # TODO
                pass
        elif not isinstance(scheme, types.FunctionType):
            raise Exception("Memorization scheme is not valid")

        state = None
        mem_op = qu.Qobj()
        N = 2**len(memories[0])
        for mem in memories:
            state = scheme(str_to_bit_arr(mem), state)

            state_ID = bit_arr_to_int(str_to_bit_arr(mem))
            mem_op += qu.ket2dm(qu.basis(N, state_ID))
        self.mem_op = qu.identity(N) - 2*mem_op
        if state.norm() > 0:
            self.memory = state.unit()
        else:
            self.memory = state
        self.memories = memories

    def get_iter_num(self, match_type, scheme="approx", mem=None, quer=None):
        if mem is None:
            mem = self.memory
        if quer is None:
            quer = self.query
        if scheme == "approx":
            B = np.sum(quer.data)/np.sqrt(quer.shape[0])
        else:
            B = quer.overlap(mem)
        B = np.abs(B)
        # print("B", B)
        w = 2*np.arcsin(B)
        # print("w", w)
        T = 2*np.pi/w
        # print("T", T)
        iter_limit = len(self.memories)
        M = find_closest_int(lambda x : T*(1/4 + x), iter_limit=iter_limit, scheme=match_type)
        return M


    def match_ezhov(self, iteration="approx"):
        if isinstance(iteration, str):
            M = self.get_iter_num("ezhov", iteration)
        elif isinstance(iteration, int):
            M = iteration
        else:
            raise Exception("Invalid iteration parameter")

        state = self.memory.copy()
        state_hist = np.zeros(M+1, dtype=qu.Qobj)
        state_hist[0] = state
        for i in range(M):
            state = self.oracle*state
            state = self.diffusion*state
            state_hist[i+1] = state
        return state, state_hist

    def match_C1(self, iteration="approx"):
        if type(iteration) is int:
            M = iteration
        else:
            M = self.get_iter_num("C1", iteration)

        state_hist = np.zeros(M+1, dtype=qu.Qobj)
        state = self.memory.copy()
        state_hist[0] = state
        state = self.oracle*state
        state = self.diffusion*state
        state_hist[1] = state
        state = self.mem_op*state
        state = self.diffusion*state
        state_hist[2] = state
        for i in range(M-2):
            state = self.oracle*state
            state = self.diffusion*state
            state_hist[i+3] = state
        return state, state_hist

    def match_C2(self, a_prime, iteration="approx"):
        ## make I_M operator
        I_M = None
        for pattern in self.patterns:
            if I_M == None:
                I_M = hamm_bin(str_to_bit_arr(pattern), a_prime)
            else:
                I_m += hamm_bin(str_to_bit_arr(pattern), a_prime)
        I_M = qu.identity(self.query.shape[0]) - 2*qu.ket2dm(I_M.unit())

        M = self.get_iter_num(iteration)

        state = self.memory.copy()
        for i in range(M-1):
            state = self.oracle*state
            state = self.diffusion*state
            if i == 0:
                state = I_M*state
                state = self.diffusion*state
        return state

    def custom_match(self, state, iterations):
        pass

    def set_oracle(self, oracle=None):
        N = self.query.shape[0]
        if oracle is None:
            self.oracle = qu.identity(N) - 2*qu.ket2dm(self.query)
        elif isinstance(oracle, qu.Qobj) and oracle.type == "ket":
            self.oracle = qu.identity(N) - 2*qu.ket2dm(oracle)
        else:
            self.oracle = oracle

    def set_diffusion(self, diffusion=None):
        if not diffusion:
            N = self.memory.shape[0]
            self.diffusion = 2*qu.ket2dm(self.memory) - qu.identity(N)
        else:
            self.diffusion = diffusion

    def set_state(self, state):
        self.state = state

    def set_max_iterations(self, iters):
        self.max_iterations = iters
