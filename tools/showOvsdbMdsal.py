#!/usr/bin/env python

import urllib2, base64, json, sys, optparse

# globals
mdsalDict = {}
CONST_DEFAULT_DEBUG=0
options = None
state = None
jsonTopologiesDict = {}

CONST_OPERATIONAL = 'operational'
CONST_CONFIG = 'config'
CONST_NET_TOPOLOGY = 'network-topology'
CONST_TOPOLOGY = 'topology'
CONST_TP_OF_INTERNAL = 65534
CONST_ALIASES = ['alpha', 'bravo', 'charlie', 'delta', 'echo', 'foxtrot', 'golf', 'hotel', 'india', 'juliet',
                 'kilo', 'lima', 'mike', 'november', 'oscar', 'papa', 'quebec', 'romeo', 'sierra', 'tango',
                 'uniform', 'victor', 'whiskey', 'xray', 'yankee', 'zulu']


class State:
    def __init__(self):
        self.nextAliasIndex = 0
        self.nextAliasWrap = 0
        self.nodeIdToAlias = {}

        self.bridgeNodes = {}
        self.ovsNodes = {}
        self.ofLinks = {}

    def __repr__(self):
        return 'State {}:{} {}:{} {}:{} {}:{} {}:{}'.format(
            'nextAliasIndex', self.nextAliasIndex,
            'nextAliasWrap', self.nextAliasWrap,
            'bridgeNodes_ids', self.bridgeNodes.keys(),
            'ovsNodes_ids', self.ovsNodes.keys(),
            'nodeIdToAlias', self.nodeIdToAlias)

    def registerBridgeNode(self, bridgeNode):
        self.bridgeNodes[bridgeNode.nodeId] = bridgeNode

    def registerOvsNode(self, ovsNode):
        self.ovsNodes[ovsNode.nodeId] = ovsNode

    def getNextAlias(self, nodeId):
        result = CONST_ALIASES[ self.nextAliasIndex ]
        if self.nextAliasWrap > 0:
            result += '_' + str(self.nextAliasWrap)

        if CONST_ALIASES[ self.nextAliasIndex ] == CONST_ALIASES[-1]:
            self.nextAliasIndex = 0
            self.nextAliasWrap += 1
        else:
            self.nextAliasIndex += 1

        self.nodeIdToAlias[ nodeId ] = result
        return result

# --

class TerminationPoint:
    def __init__(self, name, ofPort, tpType, mac='', ifaceId=''):
        self.name = name
        self.ofPort = ofPort
        self.tpType = tpType
        self.mac = mac
        self.ifaceId = ifaceId

    def __repr__(self):
        result = '{} {}:{}'.format(self.name, 'of', self.ofPort)

        if self.tpType != '':
            result += ' {}:{}'.format('type', self.tpType)
        if self.mac != '':
            result += ' {}:{}'.format('mac', self.mac)
        if self.ifaceId != '':
            result += ' {}:{}'.format('ifaceId', self.ifaceId)

        return '{' + result + '}'

# --

class BridgeNode:
    def __init__(self, nodeId, dpId, name, controllerTarget, controllerConnected):
        global state
        self.alias = state.getNextAlias(nodeId)
        self.nodeId = nodeId
        self.dpId = dpId
        self.name = name
        self.controllerTarget = controllerTarget
        self.controllerConnected = controllerConnected
        self.tps = []

    def getOpenflowName(self):
        if self.dpId is None:
            return self.nodeId
        return 'openflow:' + str( int('0x' + self.dpId.replace(':',''), 16) )

    def addTerminationPoint(self, terminationPoint):
        self.tps.append(terminationPoint)

    def __repr__(self):
        return 'BridgeNode {}:{} {}:{} {}:{} {}:{} {}:{} {}:{} {}:{} {}:{}'.format(
            'alias', self.alias,
            'nodeId', self.nodeId,
            'dpId', self.dpId,
            'openflowName', self.getOpenflowName(),
            'name', self.name,
            'controllerTarget', self.controllerTarget,
            'controllerConnected', self.controllerConnected,
            'tps', self.tps)

# --

class OvsNode:
    def __init__(self, nodeId, inetMgr, inetNode, otherLocalIp, ovsVersion):
        global state
        if inetNode != '':
            self.alias = inetNode
        else:
            self.alias = nodeId
        self.nodeId = nodeId
        self.inetMgr = inetMgr
        self.inetNode = inetNode
        self.otherLocalIp = otherLocalIp
        self.ovsVersion = ovsVersion

    def __repr__(self):
        return 'OvsNode {}:{} {}:{} {}:{} {}:{} {}:{} {}:{}'.format(
            'alias', self.alias,
            'nodeId', self.nodeId,
            'inetMgr', self.inetMgr,
            'inetNode', self.inetNode,
            'otherLocalIp', self.otherLocalIp,
            'ovsVersion', self.ovsVersion)

# ======================================================================

def printError(msg):
    sys.stderr.write(msg)

# ======================================================================

def prt(msg, logLevel=0):
    prtCommon(msg, logLevel)
def prtLn(msg, logLevel=0):
    prtCommon('{}\n'.format(msg), logLevel)
def prtCommon(msg, logLevel):
    if options.debug >= logLevel:
        sys.stdout.write(msg)

# ======================================================================

def getMdsalTreeType():
    if options.useConfigTree:
        return CONST_CONFIG
    return CONST_OPERATIONAL

# --

def grabJson(mdsalTreeType):
    global jsonTopologiesDict
    global mdsalDict

    try:
        request = urllib2.Request('http://{}:{}/restconf/{}/network-topology:network-topology/'.format(
                options.odlIp, options.odlPort, mdsalTreeType))
        # You need the replace to handle encodestring adding a trailing newline 
        # (https://docs.python.org/2/library/base64.html#base64.encodestring)
        base64string = base64.encodestring('{}:{}'.format(options.odlUsername, options.odlPassword)).replace('\n', '')
        request.add_header('Authorization', 'Basic {}'.format(base64string))   
        result = urllib2.urlopen(request)
    except urllib2.URLError, e:
        printError('Unable to send request: {}\n'.format(e))
        sys.exit(1)

    if (result.code != 200):
        printError( '{}\n{}\n\nError: unexpected code: {}\n'.format(result.info(), result.read(), result.code) )
        sys.exit(1)

    data = json.load(result)
    prtLn(data, 4)

    if not CONST_NET_TOPOLOGY in data:
        printError( '{}\n\nError: did not find {} in data'.format(data, CONST_NET_TOPOLOGY) )
        sys.exit(1)

    data2 = data[CONST_NET_TOPOLOGY]
    if not CONST_TOPOLOGY in data2:
        printError( '{}\n\nError: did not find {} in data2'.format(data2, CONST_TOPOLOGY) )
        sys.exit(1)

    jsonTopologiesDict[mdsalTreeType] = data2[CONST_TOPOLOGY]

# --

def parseJson(mdsalTreeType):
    if mdsalTreeType not in jsonTopologiesDict:
        return

    for nodeDict in jsonTopologiesDict[mdsalTreeType]:
        if not 'topology-id' in nodeDict:
            continue
        prtLn('{} {} keys are: {}'.format(mdsalTreeType, nodeDict['topology-id'], nodeDict.keys()), 3)
        if 'node' in nodeDict:
            nodeIndex = 0
            for currNode in nodeDict['node']:
                parseJsonNode('', mdsalTreeType, nodeDict['topology-id'], nodeIndex, currNode)
                nodeIndex += 1
            prtLn('', 2)
        if (mdsalTreeType == CONST_OPERATIONAL) and (nodeDict['topology-id'] == 'flow:1') and ('link' in nodeDict):
            parseJsonFlowLink(nodeDict['link'])

    prtLn('', 1)

# --

def parseJsonNode(indent, mdsalTreeType, topologyId, nodeIndex, node):
    if node.get('node-id') is None:
        printError( 'Warning: unexpected node: {}\n'.format(node) )
        return
    prt('{} {} node[{}] {} '.format(indent + mdsalTreeType, topologyId, nodeIndex, node.get('node-id')), 2)
    if 'ovsdb:bridge-name' in node:
        prtLn('', 2)
        parseJsonNodeBridge(indent + '  ', mdsalTreeType, topologyId, nodeIndex, node)
    elif 'ovsdb:connection-info' in node:
        prtLn('', 2)
        parseJsonNodeOvsdb(indent + '  ', mdsalTreeType, topologyId, nodeIndex, node)
    else:
        prtLn('keys: {}'.format(node.keys()), 2)

# --

def parseJsonNodeOvsdb(indent, mdsalTreeType, topologyId, nodeIndex, node):
    keys = node.keys()
    keys.sort()
    for k in keys:
        prtLn('{}{} : {}'.format(indent, k, node[k]), 2)

    connectionInfoRaw = node.get('ovsdb:connection-info')
    connectionInfo = {}
    if type(connectionInfoRaw) is dict:
        connectionInfo['inetMgr'] = connectionInfoRaw.get('local-ip') + ':' + str( connectionInfoRaw.get('local-port') )
        connectionInfo['inetNode'] = connectionInfoRaw.get('remote-ip') + ':' + str( connectionInfoRaw.get('remote-port') )
    otherConfigsRaw = node.get('ovsdb:openvswitch-other-configs')
    otherLocalIp = ''
    if type(otherConfigsRaw) is list:
        for currOtherConfig in otherConfigsRaw:
            if type(currOtherConfig) is dict and \
                    currOtherConfig.get('other-config-key') == 'local_ip':
                otherLocalIp = currOtherConfig.get('other-config-value')
                break

    ovsdbNode = OvsNode(node.get('node-id'), connectionInfo.get('inetMgr'), connectionInfo.get('inetNode'), otherLocalIp, node.get('ovsdb:ovs-version'))
    state.registerOvsNode(ovsdbNode)
    prtLn('Added {}'.format(ovsdbNode), 1)

# --

def parseJsonNodeBridge(indent, mdsalTreeType, topologyId, nodeIndex, node):

    controllerTarget = None
    controllerConnected = None
    controllerEntries = node.get('ovsdb:controller-entry')
    if type(controllerEntries) is list:
        for currControllerEntry in controllerEntries:
            if type(currControllerEntry) is dict:
                controllerTarget = currControllerEntry.get('target')
                controllerConnected = currControllerEntry.get('is-connected')
                break
    bridgeNode = BridgeNode(node.get('node-id'), node.get('ovsdb:datapath-id'), node.get('ovsdb:bridge-name'), controllerTarget, controllerConnected)

    keys = node.keys()
    keys.sort()
    for k in keys:
        if k == 'termination-point' and len(node[k]) > 0:
            tpIndex = 0
            for tp in node[k]:
                terminationPoint = parseJsonNodeBridgeTerminationPoint('%stermination-point[%d] :' % (indent, tpIndex), mdsalTreeType, topologyId, nodeIndex, node, tp)

                # skip boring tps
                if terminationPoint.ofPort == CONST_TP_OF_INTERNAL and \
                        (terminationPoint.name == 'br-ex' or terminationPoint.name == 'br-int'):
                    pass
                else:
                    bridgeNode.addTerminationPoint(terminationPoint)

                tpIndex += 1
        else:
            prtLn('{}{} : {}'.format(indent, k, node[k]), 2)

    state.registerBridgeNode(bridgeNode)
    prtLn('Added {}'.format(bridgeNode), 1)


# --

def parseJsonNodeBridgeTerminationPoint(indent, mdsalTreeType, topologyId, nodeIndex, node, tp):
    attachedMac = ''
    ifaceId = ''

    keys = tp.keys()
    keys.sort()
    for k in keys:
        if (k == 'ovsdb:port-external-ids' or k == 'ovsdb:interface-external-ids') and len(tp[k]) > 0:
            extIdIndex = 0
            for extId in tp[k]:
                prtLn('{} {}[{}] {} : {}'.format(indent, k, extIdIndex, extId.get('external-id-key'), extId.get('external-id-value')), 2)
                extIdIndex += 1

                if extId.get('external-id-key') == 'attached-mac':
                    attachedMac = extId.get('external-id-value')
                if extId.get('external-id-key') == 'iface-id':
                    ifaceId = extId.get('external-id-value')
        else:
            prtLn('{} {} : {}'.format(indent, k, tp[k]), 2)

    return TerminationPoint(tp.get('ovsdb:name'), 
                            tp.get('ovsdb:ofport'), 
                            tp.get('ovsdb:interface-type', '').split('-')[-1], 
                            attachedMac, ifaceId)

# --

def parseJsonFlowLink(link):
    linkCount = 0
    spc = ' ' * 2
    for currLinkDict in link:
        linkCount += 1
        linkId = currLinkDict.get('link-id')
        linkDest = currLinkDict.get('destination', {}).get('dest-tp')
        linkSrc = currLinkDict.get('source', {}).get('source-tp')

        linkDestNode = currLinkDict.get('destination', {}).get('dest-node')
        linkSrcNode = currLinkDict.get('source', {}).get('source-node')
        prtLn('{} {} {} => {}:{} -> {}:{}'.format(spc, linkCount, linkId, linkSrcNode, linkSrc.split(':')[-1], linkDestNode, linkDest.split(':')[-1]), 3)

        if linkId != linkSrc:
            printError('Warning: ignoring link with unexpected id: %s != %s\n' % (linkId, linkSrc))
            continue
        else:
            state.ofLinks[linkSrc] = linkDest

    # showOfLinks()
        
# --

def showPrettyNamesMap():
    spc = ' ' * 2
    if not options.useAlias or len(state.bridgeNodes) == 0:
        return

    prtLn('aliasMap:', 0)
    resultMap = {}
    for bridge in state.bridgeNodes.values():
        resultMap[ bridge.alias ] = bridge.getOpenflowName()

    resultMapKeys = resultMap.keys()
    resultMapKeys.sort()
    
    for resultMapKey in resultMapKeys:
        prtLn('{0}{1: <10} -> {2}'.format(spc, resultMapKey, resultMap[resultMapKey]), 0)
    prtLn('', 0)

# --

def showNodesPretty():
    if len(state.ovsNodes) == 0:
        showBridgeOnlyNodes()
        return

    aliasDict = { state.ovsNodes[nodeId].alias : nodeId for nodeId in state.ovsNodes.keys() }
    aliasDictKeys = aliasDict.keys()
    aliasDictKeys.sort()
    for ovsAlias in aliasDictKeys:
        ovsNode = state.ovsNodes[ aliasDict[ovsAlias] ]

        prt('ovsNode:{} mgr:{} version:{}'.format(ovsAlias, ovsNode.inetMgr, ovsNode.ovsVersion), 0)
        if ovsNode.inetNode.split(':')[0] != ovsNode.otherLocalIp:
            prt(' **localIp:{}'.format(ovsNode.otherLocalIp), 0)
        prtLn('', 0)
        showPrettyBridgeNodes('  ', getNodeBridgeIds(ovsNode.nodeId), ovsNode)
    showBridgeOnlyNodes(True)
    prtLn('', 0)

# --

def getNodeBridgeIds(nodeIdFilter = None):
    resultMap = {}
    for bridge in state.bridgeNodes.values():
        if nodeIdFilter is None or nodeIdFilter in bridge.nodeId:
            resultMap[ bridge.alias ] = bridge.nodeId
    resultMapKeys = resultMap.keys()
    resultMapKeys.sort()
    return [ resultMap[x] for x in resultMapKeys ]

# --

def showPrettyBridgeNodes(indent, bridgeNodeIds, ovsNode = None):
    if bridgeNodeIds is None:
        return

    for nodeId in bridgeNodeIds:
        bridgeNode = state.bridgeNodes[nodeId]
        prt('{}{}:{}'.format(indent, showPrettyName(nodeId), bridgeNode.name), 0)

        if ovsNode is None or \
                bridgeNode.controllerTarget is None or \
                bridgeNode.controllerTarget == '' or \
                ovsNode.inetMgr.split(':')[0] != bridgeNode.controllerTarget.split(':')[-2] or \
                bridgeNode.controllerConnected != True:
            prt(' controller:{}'.format(bridgeNode.controllerTarget), 0)
            prt(' connected:{}'.format(bridgeNode.controllerConnected), 0)
        prtLn('', 0)
        showPrettyTerminationPoints(indent + '  ', bridgeNode.tps)

# --

def showBridgeOnlyNodes(showOrphansOnly = False):
    if len(state.bridgeNodes) == 0:
        return

    # group bridges by nodeId prefix
    resultMap = {}
    for bridge in state.bridgeNodes.values():
        nodePrefix = bridge.nodeId.split('/bridge/')[0]

        if showOrphansOnly and nodePrefix in state.ovsNodes:
            continue

        if nodePrefix in resultMap:
            resultMap[nodePrefix][bridge.alias] = bridge.nodeId
        else:
            resultMap[nodePrefix] = { bridge.alias: bridge.nodeId }
    resultMapKeys = resultMap.keys()
    resultMapKeys.sort()

    if len(resultMapKeys) == 0:
        return  #noop

    for nodePrefix in resultMapKeys:
        nodePrefixEntriesKeys = resultMap[nodePrefix].keys()
        nodePrefixEntriesKeys.sort()
        # prtLn('Bridges in {}: {}'.format(nodePrefix, nodePrefixEntriesKeys), 0)
        prtLn('Bridges in {}'.format(nodePrefix), 0)
        nodeIds = [ resultMap[nodePrefix][nodePrefixEntry] for nodePrefixEntry in nodePrefixEntriesKeys ]
        showPrettyBridgeNodes('  ', nodeIds)

    prtLn('', 0)

# --

def showPrettyTerminationPoints(indent, tps):

    tpsDict = {}
    for tp in tps:
        tpsDict[ tp.ofPort ] = tp

    tpDictKeys = tpsDict.keys()
    tpDictKeys.sort()
    for tpKey in tpDictKeys:
        tp = tpsDict[tpKey]
        prt('{}of:{} {}'.format(indent, tp.ofPort, tp.name), 0)
        if tp.mac != '':
            prt(' {}:{}'.format('mac', tp.mac), 0)
        if tp.ifaceId != '':
            prt(' {}:{}'.format('ifaceId', tp.ifaceId), 0)

        prtLn('', 0)

# --

def showPrettyName(name):
    if not options.useAlias:
        return name

    # handle both openflow:138604958315853:2 and openflow:138604958315853 (aka dpid)
    # also handle ovsdb://uuid/5c72ec51-1e71-4a04-ab0b-b044fb5f4dc0/bridge/br-int  (aka nodeId)
    #
    nameSplit = name.split(':')
    ofName = ':'.join(nameSplit[:2])
    ofPart = ''
    if len(nameSplit) > 2:
        ofPart = ':' + ':'.join(nameSplit[2:])

    for bridge in state.bridgeNodes.values():
        if bridge.getOpenflowName() == ofName or bridge.nodeId == name:
            return '{}{}'.format(bridge.alias, ofPart)

    # not found, return paramIn
    return name

# --

def showOfLinks():
    spc = ' ' * 2
    ofLinksKeys = state.ofLinks.keys()
    ofLinksKeys.sort()
    ofLinksKeysVisited = set()

    if len(ofLinksKeys) == 0:
        # prtLn('no ofLinks found\n', 0)
        return

    prtLn('ofLinks (discover via lldp):', 0)
    for ofLinkKey in ofLinksKeys:
        if ofLinkKey in ofLinksKeysVisited:
            continue
        if state.ofLinks.get( state.ofLinks[ofLinkKey] ) == ofLinkKey:
            prtLn('{}{} <-> {}'.format(spc, showPrettyName(ofLinkKey), showPrettyName(state.ofLinks[ofLinkKey])), 0)
            ofLinksKeysVisited.add(state.ofLinks[ofLinkKey])
        else:
            prtLn('{}{} -> {}'.format(spc, showPrettyName(ofLinkKey), showPrettyName(state.ofLinks[ofLinkKey])), 0)
        ofLinksKeysVisited.add(ofLinkKey)
    prtLn('', 0)

# --

def parseArgv():
    global options

    parser = optparse.OptionParser(version="0.1")
    parser.add_option("-d", "--debug", action="count", dest="debug", default=CONST_DEFAULT_DEBUG, 
                      help="Verbosity. Can be provided multiple times for more debug.")
    parser.add_option("-n", "--noalias", action="store_false", dest="useAlias", default=True,
                      help="Do not map nodeId of bridges to an alias")
    parser.add_option("-i", "--ip", action="store", type="string", dest="odlIp", default="localhost",
                      help="opendaylights ip address")
    parser.add_option("-t", "--port", action="store", type="string", dest="odlPort", default="8080",
                      help="opendaylights listening tcp port on restconf northbound")
    parser.add_option("-u", "--user", action="store", type="string", dest="odlUsername", default="admin",
                      help="opendaylight restconf username")
    parser.add_option("-p", "--password", action="store", type="string", dest="odlPassword", default="admin",
                      help="opendaylight restconf password")
    parser.add_option("-c", "--config", action="store_true", dest="useConfigTree", default=False,
                      help="parse mdsal restconf config tree instead of operational tree")

    (options, args) = parser.parse_args(sys.argv)
    prtLn('argv options:{} args:{}'.format(options, args), 2)

# --

def doMain():
    global state

    state = State()
    parseArgv()
    grabJson(getMdsalTreeType())
    parseJson(getMdsalTreeType())
    showPrettyNamesMap()
    showNodesPretty()
    showOfLinks()

# --

if __name__ == "__main__":
    doMain()
    sys.exit(0)
