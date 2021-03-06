""" Dumb CloudFormation emulator """

from boto import ec2
import json
import logging
import string
import random
import time


class FakeCF_Exception(Exception):
    """
    Exception for FakeCF
    """
    pass


class FakeCFResource(object):
    """
    Class for representing Resource
    """
    def __init__(self, physical_resource_id, resource_type):
        self.physical_resource_id = physical_resource_id
        self.resource_type = resource_type


class FakeCFEvent(object):
    """
    Class for representing Event
    """
    def __init__(self, resource_type, resource_status):
        self.resource_type = resource_type
        self.resource_status = resource_status
        self.time = time.time()


class FakeCF(object):
    """
    CloudFormation emulator
    """

    def __init__(self, aws_access_key_id, aws_secret_access_key, region):
        """
        Create FakeCF object

        @param aws_access_key_id: AWS Access Key
        @type aws_access_key_id: str

        @param aws_secret_access_key: AWS Secret Key
        @type aws_secret_access_key: str

        @param region: AWS Region
        @type region: str
        """
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region = region
        self.conn = ec2.connect_to_region(region,
                                          aws_access_key_id=aws_access_key_id,
                                          aws_secret_access_key=aws_secret_access_key)
        if not self.conn:
            raise FakeCF_Exception('Failed to connect to EC2 region %s with provided credentials'
                                   % region)
        self.stacks = {}
        self.events = {}
        self.resources = {}

    def describe_stack_resources(self, stack_id):
        """
        Describe resources in stack

        @param stack_id: stack id
        @type stack_id: str

        @return: list of resources
        @rtype: list of L{FakeCFResource}

        @raises FakeCF_Exception
        """
        if stack_id in self.resources:
            return self.resources[stack_id][:]
        else:
            raise FakeCF_Exception('Failed to get stack with id %s for describing resources' % stack_id)

    def describe_stack_events(self, stack_id):
        """
        Describe events for stack

        @param stack_id: stack id
        @type stack_id: str

        @return: list of resources
        @rtype: list of L{FakeCFEvent}

        @raises FakeCF_Exception
        """
        if stack_id in self.events:
            return self.events[stack_id][:]
        else:
            raise FakeCF_Exception('Failed to get stack with id %s for describing events' % stack_id)

    def create_stack(self, stack_id, template_body, parameters=[], timeout_in_minutes=10):
        """
        Create stack

        @param stack_id: stack id
        @type stack_id: str

        @param template_body: JSON template
        @type template_body: str

        @param parameters: parameters used in template (name, value)
        @type parameters: list of (str, str)

        @param timeout_in_minutes: timeout in minutes
        @type timeout_in_minutes: int

        @raises FakeCF_Exception
        """
        self.stacks[stack_id] = {}
        self.events[stack_id] = []
        self.resources[stack_id] = []

        self.stacks[stack_id]['json_def'] = json.loads(template_body)
        self.stacks[stack_id]['parameters'] = {}
        for param, value in parameters:
            self.stacks[stack_id]['parameters'][param] = value
        self.stacks[stack_id]['stack_id'] = stack_id
        self.stacks[stack_id]['stack_random_add'] = ''.join(random.choice(string.ascii_lowercase) for x in range(4))

        self.events[stack_id].append(FakeCFEvent('AWS::CloudFormation::Stack',
                                                 'CREATE_IN_PROGRESS'))

        for token in self.stacks[stack_id]['json_def']:
            if not token in ['Description', 'Parameters', 'AWSTemplateFormatVersion',
                             'Outputs', 'Resources', 'Mappings']:
                raise FakeCF_Exception('Unknown token %s ' % token)
            for mandatory_key in ['AWSTemplateFormatVersion', 'Resources']:
                if not mandatory_key in self.stacks[stack_id]['json_def']:
                    raise FakeCF_Exception('%s is not set' % mandatory_key)
            if self.stacks[stack_id]['json_def']['AWSTemplateFormatVersion'] != '2010-09-09':
                raise FakeCF_Exception('Unknown AWSTemplateFormatVersion version: %s'
                                       % self.stacks[stack_id]['json_def']['AWSTemplateFormatVersion'])

        waitlist = []

        for resource in self.stacks[stack_id]['json_def']['Resources']:
            # Doing check and creating security groups
            resource_def = self._calc_(stack_id, self.stacks[stack_id]['json_def']['Resources'][resource], 0)
            resource_name = self._gen_resource_name(stack_id, resource)
            if type(resource_def) != dict or not 'Type' in resource_def:
                raise FakeCF_Exception('Broken resource %s definition: %s' % (resource, resource_def))
            if resource_def['Type'] == 'AWS::EC2::SecurityGroup':
                self._create_sg(resource_name, resource_def)

        for resource in self.stacks[stack_id]['json_def']['Resources']:
            # Creating instances
            resource_def = self._calc_(stack_id, self.stacks[stack_id]['json_def']['Resources'][resource], 0)
            resource_name = self._gen_resource_name(stack_id, resource)
            if resource_def['Type'] == 'AWS::EC2::Instance':
                reservation = self._create_instance(resource_name, resource_def)
                waitlist.append(reservation)

        waitstart = time.time()
        for reservation in waitlist:
            while reservation.instances[0].update() == 'pending':
                if time.time() - waitstart > 60 * timeout_in_minutes:
                    # Timeout :-(
                    FakeCF_Exception('Timeout while creating stack')
                time.sleep(5)
            instance_state = reservation.instances[0].update()
            if instance_state == 'running':
                self.resources[stack_id].append(FakeCFResource(reservation.instances[0].__dict__['id'],
                                                               'AWS::EC2::Instance'))
            else:
                raise FakeCF_Exception('Instance %s creation failure!' % reservation)
        self.events[stack_id].append(FakeCFEvent('AWS::CloudFormation::Stack', 'CREATE_COMPLETE'))

    def _gen_resource_name(self, stack_id, name):
        """
        Generate unique resource name (internal)

        @param stack_id: stack id
        @type stack_id: str

        @param name: Resource's name
        @type name: str

        @return: unique resource name
        @rtype: str
        """
        return self.stacks[stack_id]['stack_id'] + \
            '-' + name + '-' + self.stacks[stack_id]['stack_random_add']

    def _calc_(self, stack_id, token, level):
        """
        Calculate expression (internal)

        @param stack_id: stack id
        @type stack_id: str

        @param token: token to calculate
        @type token: str or list or dict

        @param level: level of recursion we are currently on
        @type level: int

        @return: calculated token
        @rtype: str or list or dict

        @raises FakeCF_Exception
        """
        logging.debug('Calc%i: %s', level, token)
        result = None
        if type(token) == str or type(token) == unicode:
            result = token
        elif type(token) == list:
            result = []
            for token_new in token:
                result.append(self._calc_(stack_id, token_new, level + 1))
        elif type(token) == dict:
            if len(token) == 0:
                result = {}
            elif len(token) > 1:
                result = {}
                for token_new_key in token:
                    result[self._calc_(stack_id, token_new_key, level + 1)] = \
                        self._calc_(stack_id, token[token_new_key], level + 1)
            else:  # len == 1
                key = token.keys()[0]
                if key == 'Ref':
                    result = self._Ref(stack_id,
                                       self._calc_(stack_id, token[key], level + 1),
                                       level + 1)
                elif key == 'Fn::Join':
                    result = self._fn_Join(stack_id, token[key], level + 1)
                elif key == 'Fn::FindInMap':
                    result = self._fn_FindInMap(stack_id,
                                                self._calc_(stack_id,
                                                            token[key],
                                                            level + 1),
                                                level + 1)
                elif key == 'Fn::GetAtt':
                    result = self._fn_GetAtt(stack_id, token[key], level + 1)
                else:
                    result = {key: self._calc_(stack_id, token[key], level + 1)}
        logging.debug('Calc%i result: %s', level, result)
        return result

    def _Ref(self, stack_id, param, level):
        """
        Calculate Ref function (internal)

        @param stack_id: stack id
        @type stack_id: str

        @param param: argument
        @type param: str

        @param level: level of recursion we are currently on
        @type level: int

        @return: calculated value
        @rtype: str

        @raises FakeCF_Exception
        """
        logging.debug('Ref%i: %s', level, param)
        if not 'Parameters' in self.stacks[stack_id]['json_def']:
            raise FakeCF_Exception('No parameters in JSON, %s queried' % param)
        if param in self.stacks[stack_id]['json_def']['Parameters']:
            if not param in self.stacks[stack_id]['parameters']:
                raise FakeCF_Exception('Parameter %s is not set' % param)
            result = self.stacks[stack_id]['parameters'][param]
        elif param in self.stacks[stack_id]['json_def']['Resources']:
            result = self._gen_resource_name(stack_id, param)
        elif param == 'AWS::Region':
            result = self.region
        logging.debug('Ref%i result: %s', level, result)
        return result

    def _fn_FindInMap(self, stack_id, params, level):
        """
        Calculate fn_FindInMap function (internal)

        @param stack_id: stack id
        @type stack_id: str

        @param params: list of arguments
        @type param: list

        @param level: level of recursion we are currently on
        @type level: int

        @return: calculated value
        @rtype: str

        @raises FakeCF_Exception
        """
        logging.debug('FindInMap%i: %s', level, params)
        if type(params) != list or len(params) != 3:
            raise FakeCF_Exception('Wrong parameter for fn::FindInMap: %s' % params)
        param_map = params[0]
        param_arg = params[1]
        param_ret = params[2]
        if not 'Mappings' in self.stacks[stack_id]['json_def']:
            raise FakeCF_Exception('No mappings JSON, %s required' % param_map)
        if type(self.stacks[stack_id]['json_def']['Mappings']) != dict or \
                not param_map in self.stacks[stack_id]['json_def']['Mappings']:
            raise FakeCF_Exception('No %s mapping' % param_map)
        required_map = self.stacks[stack_id]['json_def']['Mappings'][param_map]
        if type(required_map) != dict or not param_arg in required_map:
            raise FakeCF_Exception('No %s in %s' % (param_arg, param_map))
        required_val = required_map[param_arg]
        if type(required_val) != dict or not param_ret in required_val:
            raise FakeCF_Exception('No %s in %s' % (param_ret, required_val))
        result = required_val[param_ret]
        logging.debug('FindInMap%i result: %s', level, result)
        return result

    def _fn_Join(self, stack_id, params, level):
        """
        Calculate fn_Join function (internal)

        @param stack_id: stack id
        @type stack_id: str

        @param params: list of arguments
        @type param: list

        @param level: level of recursion we are currently on
        @type level: int

        @return: calculated value
        @rtype: str

        @raises FakeCF_Exception
        """
        logging.debug('Join%i: %s', level, params)
        if type(params) != list or len(params) < 2:
            raise FakeCF_Exception('Wrong parameter for fn::Join: %s' % params)
        delim = self._calc_(stack_id, params[0], level + 1)
        result = delim.join(self._calc_(stack_id, x, level + 1) for x in params[1])
        logging.debug('Join result%i: %s', level, result)
        return result

    @staticmethod
    def _fn_GetAtt(stack_id, params, level):
        """
        Calculate fn_GetAtt function (internal)

        @param stack_id: stack id
        @type stack_id: str

        @param params: list of arguments
        @type param: list

        @param level: level of recursion we are currently on
        @type level: int

        @return: calculated value
        @rtype: str

        @raises FakeCF_Exception
        """
        raise FakeCF_Exception('Not implemented')
        return None

    def _create_sg(self, name, params):
        """
        Create Security group (internal)

        @param name: name of the security group
        @type name: str

        @param params: list of arguments
        @type param: list

        @raises FakeCF_Exception
        """

        logging.debug('Creating Security group %s: %s', name, params)
        try:
            if 'GroupDescription' in params['Properties']:
                description = params['Properties']['GroupDescription']
            else:
                description = name
            vpc_id = None
            if 'VpcId' in params['Properties']:
                vpc_id = params['Properties']['VpcId']
            sgroup = self.conn.create_security_group(name,
                                                     description,
                                                     vpc_id=vpc_id)
            time.sleep(3)
            if 'SecurityGroupIngress' in params['Properties']:
                for rule in params['Properties']['SecurityGroupIngress']:
                    sgroup.authorize(rule['IpProtocol'],
                                     rule['FromPort'],
                                     rule['ToPort'],
                                     rule['CidrIp'])
        except:
            raise FakeCF_Exception('Creating Security group %s failed!' % name)
        logging.info('Security group %s created!', name)

    def _create_instance(self, name, params):
        """
        Create Instance (internal)

        @param name: name of the security group
        @type name: str

        @param params: list of arguments
        @type param: list

        @return: reservation id
        @rtype: L{boto.ec2.instance.Reservation}

        @raises FakeCF_Exception
        """
        logging.debug('Creating Instance %s: %s', name, params)
        reservation = None
        try:
            image_id = params['Properties']['ImageId']
            instance_type = 'm1.small'
            if 'InstanceType' in params['Properties']:
                instance_type = params['Properties']['InstanceType']
            subnet_id = None
            if 'SubnetId' in params['Properties']:
                subnet_id = params['Properties']['SubnetId']
            key_name = None
            if 'KeyName' in params['Properties']:
                key_name = params['Properties']['KeyName']
            security_groups = None
            if 'SecurityGroups' in params['Properties']:
                security_groups = params['Properties']['SecurityGroups']
            security_group_ids = None
            if 'SecurityGroupIds' in params['Properties']:
                security_group_ids = self._find_sg_ids(params['Properties']['SecurityGroupIds'])
            reservation = self.conn.run_instances(image_id,
                                                 key_name=key_name,
                                                 security_groups=security_groups,
                                                 instance_type=instance_type,
                                                 subnet_id=subnet_id,
                                                 security_group_ids=security_group_ids)
            time.sleep(3)
            if 'Tags' in params['Properties']:
                for tag in params['Properties']['Tags']:
                    reservation.instances[0].add_tag(tag['Key'], tag['Value'])
        except Exception, err:
            raise FakeCF_Exception('Creating Instance %s failed: %s'
                                   % (name, err))
        logging.info('Instance %s created!', name)
        return reservation

    def _find_sg_ids(self, namelist):
        """
        Find Security group ids (internal)

        @param namelist: list of security group names
        @type namelist: list

        @return: list of security group ids
        @rtype: list

        @raises FakeCF_Exception
        """
        result = []
        for sgroup in self.conn.get_all_security_groups():
            if sgroup.name in namelist or sgroup.id in namelist:
                result.append(sgroup.id)
        if len(result) != len(namelist):
            raise FakeCF_Exception('Failed to locate requires VPC groups: %s'
                                   % namelist)
        return result

__all__ = ['FakeCF', 'FakeCFEvent', 'FakeCFResource', 'FakeCF_Exception']
