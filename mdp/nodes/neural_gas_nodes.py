__docformat__ = "restructuredtext en"

from mdp import numx, numx_rand, utils, graph, Node

class _GNGNodeData(object):
    """Data associated to a node in a Growing Neural Gas graph."""
    def __init__(self, pos, error=0.0, hits=0, label=None):
        # reference vector (spatial position)
        self.pos = pos
        # cumulative error
        self.cum_error = error
        self.hits = 0
        self.label = label

class _GNGEdgeData(object):
    """Data associated to an edge in a Growing Neural Gas graph."""
    def __init__(self, age=0):
        self.age = age
    def inc_age(self):
        self.age += 1


class GrowingNeuralGasNode(Node):
    """Learn the topological structure of the input data by building a
    corresponding graph approximation.

    More information about the Growing Neural Gas algorithm can be found in
    B. Fritzke, A Growing Neural Gas Network Learns Topologies, in G. Tesauro,
    D. S. Touretzky, and T. K. Leen (editors), Advances in Neural Information
    Processing Systems 7, pages 625-632. MIT Press, Cambridge MA, 1995.

    A java implementation is available at:
    http://www.neuroinformatik.ruhr-uni-bochum.de/ini/VDM/research/gsn/DemoGNG/GNG.html

    **Attributes and methods of interest**

    - graph -- The corresponding `mdp.graph.Graph` object
    """
    def __init__(self, start_poss=None, eps_b=0.2, eps_n=0.006, max_age=50,
                 lambda_=100, alpha=0.5, d=0.995, max_nodes=2147483647,
                 input_dim=None, dtype=None):
        """Growing Neural Gas algorithm.

        :Parameters:

          start_poss
            sequence of two arrays containing the position of the
            first two nodes in the GNG graph. In unspecified, the
            initial nodes are chosen with a random position generated
            from a gaussian distribution with zero mean and unit
            variance.

          eps_b
            coefficient of movement of the nearest node to a new data
            point. Typical values are 0 < eps_b << 1 .

            Default: 0.2

          eps_n
            coefficient of movement of the neighbours of the nearest
            node to a new data point. Typical values are
            0 < eps_n << eps_b .

            Default: 0.006

          max_age
            remove an edge after `max_age` updates. Typical values are
            10 < max_age < lambda.

            Default: 50

          `lambda_`
            insert a new node after `lambda_` steps. Typical values are O(100).

            Default: 100

          alpha
            when a new node is inserted, multiply the error of the
            nodes from which it generated by 0<alpha<1. A typical value
            is 0.5.

            Default: 0.5

          d
            each step the error of the nodes are multiplied by 0<d<1.
            Typical values are close to 1.

            Default: 0.995

          max_nodes
            maximal number of nodes in the graph.

            Default: 2^31 - 1
        """
        self.graph = graph.Graph()
        self.tlen = 0

        #copy parameters
        (self.eps_b, self.eps_n, self.max_age, self.lambda_, self.alpha,
         self.d, self.max_nodes) = (eps_b, eps_n, max_age, lambda_, alpha,
                                    d, max_nodes)


        super(GrowingNeuralGasNode, self).__init__(input_dim, None, dtype)

        if start_poss is not None:
            if self.dtype is None:
                self.dtype = start_poss[0].dtype
            node1 = self._add_node(self._refcast(start_poss[0]))
            node2 = self._add_node(self._refcast(start_poss[1]))
            self._add_edge(node1, node2)

    def _set_input_dim(self, n):
        self._input_dim = n
        self.output_dim = n

    def _add_node(self, pos):
        node = self.graph.add_node(_GNGNodeData(pos))
        return node

    def _add_edge(self, from_, to_):
        self.graph.add_edge(from_, to_, _GNGEdgeData())

    def _get_nearest_nodes(self, x):
        """Return the two nodes in the graph that are nearest to x and their
        squared distances. (Return ([node1, node2], [dist1, dist2])"""
        # distance function
        def _distance_from_node(node):
            #return norm(node.data.pos-x)**2
            tmp = node.data.pos - x
            return utils.mult(tmp, tmp)
        g = self.graph
        # distances of all graph nodes from x
        distances = numx.array(map(_distance_from_node, g.nodes))
        ids = distances.argsort()[:2]
        #nearest = [g.nodes[idx] for idx in ids]
        #return nearest, distances[ids]
        return (g.nodes[ids[0]], g.nodes[ids[1]]), distances.take(ids)

    def _move_node(self, node, x, eps):
        """Move a node by eps in the direction x."""
        # ! make sure that eps already has the right dtype
        node.data.pos += eps*(x - node.data.pos)

    def _remove_old_edges(self, edges):
        """Remove all edges older than the maximal age."""
        g, max_age = self.graph, self.max_age
        for edge in self.graph.edges:
            if edge.data.age > max_age:
                g.remove_edge(edge)
                if edge.head.degree() == 0:
                    g.remove_node(edge.head)
                if edge.tail.degree() == 0:
                    g.remove_node(edge.tail)

    def _insert_new_node(self):
        """Insert a new node in the graph where it is more necessary (i.e.
        where the error is the largest)."""
        g = self.graph
        # determine the node with the highest error
        errors = map(lambda x: x.data.cum_error, g.nodes)
        qnode = g.nodes[numx.argmax(errors)]
        # determine the neighbour with the highest error
        neighbors = qnode.neighbors()
        errors = map(lambda x: x.data.cum_error, neighbors)
        fnode = neighbors[numx.argmax(errors)]
        # new node, halfway between the worst node and the worst of
        # its neighbors
        new_pos = 0.5*(qnode.data.pos + fnode.data.pos)
        new_node = self._add_node(new_pos)
        # update edges
        edges = qnode.get_edges(neighbor=fnode)
        g.remove_edge(edges[0])
        self._add_edge(qnode, new_node)
        self._add_edge(fnode, new_node)
        # update errors
        qnode.data.cum_error *= self.alpha
        fnode.data.cum_error *= self.alpha
        new_node.data.cum_error = 0.5*(qnode.data.cum_error+
                                       fnode.data.cum_error)

    def get_nodes_position(self):
        return numx.array(map(lambda n: n.data.pos, self.graph.nodes),
                          dtype = self.dtype)

    def _train(self, input):
        g = self.graph
        d = self.d

        if len(g.nodes)==0:
            # if missing, generate two initial nodes at random
            # assuming that the input data has zero mean and unit variance,
            # choose the random position according to a gaussian distribution
            # with zero mean and unit variance
            normal = numx_rand.normal
            self._add_node(self._refcast(normal(0.0, 1.0, self.input_dim)))
            self._add_node(self._refcast(normal(0.0, 1.0, self.input_dim)))

        # loop on single data points
        for x in input:
            self.tlen += 1

            # step 2 - find the nearest nodes
            # dists are the squared distances of x from n0, n1
            (n0, n1), dists = self._get_nearest_nodes(x)

            # step 3 - increase age of the emanating edges
            for e in n0.get_edges():
                e.data.inc_age()

            # step 4 - update error
            n0.data.cum_error += numx.sqrt(dists[0])

            # step 5 - move nearest node and neighbours
            self._move_node(n0, x, self.eps_b)
            # neighbors undirected
            neighbors = n0.neighbors()
            for n in neighbors:
                self._move_node(n, x, self.eps_n)

            # step 6 - update n0<->n1 edge
            if n1 in neighbors:
                # should be one edge only
                edges = n0.get_edges(neighbor=n1)
                edges[0].data.age = 0
            else:
                self._add_edge(n0, n1)

            # step 7 - remove old edges
            self._remove_old_edges(n0.get_edges())

            # step 8 - add a new node each lambda steps
            if not self.tlen % self.lambda_ and len(g.nodes) < self.max_nodes:
                self._insert_new_node()

            # step 9 - decrease errors
            for node in g.nodes:
                node.data.cum_error *= d

    def nearest_neighbor(self, input):
        """Assign each point in the input data to the nearest node in
        the graph. Return the list of the nearest node instances, and
        the list of distances.
        Executing this function will close the training phase if
        necessary."""
        super(GrowingNeuralGasNode, self).execute(input)

        nodes = []
        dists = []
        for x in input:
            (n0, n1), dist = self._get_nearest_nodes(x)
            nodes.append(n0)
            dists.append(numx.sqrt(dist[0]))
        return nodes, dists
