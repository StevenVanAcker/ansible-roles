#!/usr/bin/env python3

import boto3
import pprint

def debug(msg):
    print("[DEBUG] {}".format(msg))

def listNetworks():
    client = boto3.client('ec2')
    response = client.describe_vpcs()
    #if len(response["Vpcs"]) > 0:
    #    print("ID          \tIP-Range\t(Name)")
        
    for vpc in response["Vpcs"]:
        names = [x["Value"] for x in vpc["Tags"] if x["Key"] == "Name"]
        print("{}\t{}{}".format(vpc["VpcId"], vpc["CidrBlock"], "\t({})".format(names[0]) if len(names) > 0 else ""))

        response = client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc["VpcId"]]}])
        if len(response["Subnets"]) > 0:
            subnetids = [(x["SubnetId"], x["CidrBlock"]) for x in response["Subnets"]]
            for (snid,ipr) in subnetids:
                print("    {}   ({})".format(snid, ipr))

def deleteNetwork(iprange):
    client = boto3.client('ec2')
    response = client.describe_vpcs(Filters=[{'Name':'cidr', 'Values':[iprange]}])
    if len(response["Vpcs"]) > 0:
        vpcid = response["Vpcs"][0]["VpcId"]
        debug("Found VPC with IP-range {} and ID {}".format(iprange, vpcid))

        # delete internet gateway if any
        response = client.describe_internet_gateways(Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpcid]}])
        if len(response["InternetGateways"]) > 0:
            igwids = [x["InternetGatewayId"] for x in response["InternetGateways"]]
            for x in igwids:
                debug("Detaching internet gateway {}".format(x))
                client.detach_internet_gateway(InternetGatewayId=x, VpcId=vpcid)
                debug("Removing internet gateway {}".format(x))
                client.delete_internet_gateway(InternetGatewayId=x)

        # delete subnets if any
        response = client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpcid]}])
        if len(response["Subnets"]) > 0:
            subnetids = [x["SubnetId"] for x in response["Subnets"]]
            for x in subnetids:
                debug("Removing attached subnet {}".format(x))
                client.delete_subnet(SubnetId=x)

        debug("Removing VPC {}".format(vpcid))    
        client.delete_vpc(VpcId=vpcid)
    else:
        debug("No VPC found with IP-range {}".format(iprange))

def createNetwork(iprange, tcpports=[], udpports=[]):
    newresources = []
    linkedresources = []
    client = boto3.client('ec2')

    # Create VPC
    response = client.create_vpc(CidrBlock=iprange)
    vpcid = response["Vpc"]["VpcId"]
    newresources += [vpcid]
    debug("Created new VPC with ID {}".format(vpcid))

    # Retrieve the default security group associated with this VPC
    response = client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpcid]}])
    sgid = response['SecurityGroups'][0]['GroupId']
    linkedresources += [sgid]
    debug("VPC has default security group ID {}".format(sgid))

    # Add firewall rules
    if len(tcpports) > 0:
        debug("Allowing inbound traffic to TCP ports: {}".format(tcpports))
        client.authorize_security_group_ingress(GroupId=sgid,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "IpRanges": [ { "CidrIp": "0.0.0.0/0" } ],
                "FromPort": port,
                "ToPort": port
            } for port in tcpports]
        )

    if len(udpports) > 0:
        debug("Allowing inbound traffic to UDP ports: {}".format(udpports))
        client.authorize_security_group_ingress(GroupId=sgid,
            IpPermissions=[{
                "IpProtocol": "udp",
                "IpRanges": [ { "CidrIp": "0.0.0.0/0" } ],
                "FromPort": port,
                "ToPort": port
            } for port in udpports]
        )

    # Create subnet
    response = client.create_subnet(CidrBlock=iprange, VpcId=vpcid)
    subnetid = response["Subnet"]["SubnetId"]
    newresources += [subnetid]
    debug("Created subnet {} with ID {}".format(iprange, subnetid))

    # Create gateway
    response = client.create_internet_gateway()
    igwid = response["InternetGateway"]["InternetGatewayId"]
    newresources += [igwid]
    debug("Created internet gateway with ID {}".format(igwid))

    # attach gateway to VPC
    debug("Attaching internet gateway with ID {} to VPC with ID {}".format(igwid, vpcid))
    response = client.attach_internet_gateway(InternetGatewayId=igwid, VpcId=vpcid)

    # find default route table
    response = client.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpcid]}])
    rtid = response['RouteTables'][0]['RouteTableId']
    linkedresources += [rtid]
    debug("Route table of internet gateway with ID {} has ID {}".format(igwid, rtid))
    
    # add internet gateway to route table
    response = client.create_route(DestinationCidrBlock='0.0.0.0/0', GatewayId=igwid, RouteTableId=rtid)
    debug("Addedinternet gateway with ID {} as default gateway to route table with ID {}".format(igwid, rtid))

    return (newresources, linkedresources)

def nameResources(name, resources):
    client = boto3.client('ec2')
    debug("Adding resources with 'Name' tag \"{}\": {}".format(name, resources))
    client.create_tags(Resources=resources, Tags=[{'Key': 'Name', 'Value': name}])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create or remove a VPC network on Amazon EC2")
    subparsers = parser.add_subparsers(dest="cmd")

    create = subparsers.add_parser('create')
    create.add_argument('iprange', type=str, help="The IP range in CIDR format, no bigger than /16")
    create.add_argument('--name', dest="name", type=str, default="", help="A name all resources linked to this network will be tagged with", nargs='?')
    create.add_argument('--tcp', dest="tcp", type=str, default="", help="List of TCP ports to allow ingress traffic to. E.g.: 22,80", nargs='?')
    create.add_argument('--udp', dest="udp", type=str, default="", help="List of UDP ports to allow ingress traffic to. E.g.: 53,123", nargs='?')

    remove = subparsers.add_parser('remove')
    remove.add_argument('iprange', type=str, help="The IP range in CIDR format to remove")

    listcmd = subparsers.add_parser('list')

    args = parser.parse_args()

    if args.cmd == "create":
        tcpports = [int(x) for x in args.tcp.split(",")] if args.tcp != "" else []
        udpports = [int(x) for x in args.udp.split(",")] if args.udp != "" else []
        newresources, linkedresources = createNetwork(args.iprange, tcpports=tcpports, udpports=udpports)
        nameResources(args.name, newresources + linkedresources)
    elif args.cmd == "remove":
        deleteNetwork(args.iprange)
    elif args.cmd == "list":
        listNetworks()
    else:
        parser.print_help()

