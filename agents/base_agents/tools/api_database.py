import pandas as pd
import sqlite3

API_DATABASE_FILE = "api.sqlite"

def save_df_to_sqlite(df: pd.DataFrame, database_path: str, table_name: str):
    conn = sqlite3.connect(database=database_path)
    df.to_sql(table_name, conn, if_exists='replace', index=False)

def load_df_from_sqlite(database_path: str, table_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(database=database_path)
    df = pd.read_sql_query("SELECT * FROM " + table_name, conn)
    return df

def search_from_sqlite(database_path: str, table_name: str, condition: str) -> pd.DataFrame:
    conn = sqlite3.connect(database=database_path)
    query = f"SELECT * FROM {table_name} WHERE {condition}"
    df = pd.read_sql_query(query, conn)
    return df

def init_api_database():
    conn = sqlite3.connect(API_DATABASE_FILE)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS api_info;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_info (
            name TEXT PRIMARY KEY,
            method TEXT NOT NULL,
            uri TEXT NOT NULL,
            description TEXT
        )''')
    
    cursor.execute('DROP TABLE IF EXISTS uri_parameters;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uri_parameters (
            api_name TEXT NOT NULL,
            parameter TEXT NOT NULL,
            mandatory BOOLEAN NOT NULL,
            type TEXT,
            description TEXT,
            PRIMARY KEY (api_name, parameter)
        )''')
    
    cursor.execute('DROP TABLE IF EXISTS request_parameters;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_parameters (
            api_name TEXT NOT NULL,
            table_id INTEGER NOT NULL,
            parameter TEXT NOT NULL,
            mandatory BOOLEAN NOT NULL,
            type TEXT,
            description TEXT,
            PRIMARY KEY (api_name, table_id, parameter)
        )''')
    
    conn.commit()
    conn.close()
    return

def insert_data():
    conn = sqlite3.connect(API_DATABASE_FILE)
    cursor = conn.cursor()

    api_info_data = [
        # (name, method, uri, description)
        ("创建云服务器", "POST", "https://{endpoint}/v1.1/{project_id}/cloudservers", "创建一台或多台云服务器。"),
        ("删除云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/delete", "根据指定的云服务器ID列表，删除云服务器。"),
        ("查询云服务器详情", "GET", "https://{endpoint}/v1/{project_id}/cloudservers/{server_id}", "查询弹性云服务器的详细信息。"),
        ("查询云服务器详情列表", "GET", "https://{endpoint}/v1/{project_id}/cloudservers/detail?flavor={flavor}&name={name}&status={status}&limit={limit}&offset={offset}&not-tags={not-tags}&reservation_id={reservation_id}&enterprise_project_id={enterprise_project_id}&tags={tags}&ip={ip}", "根据用户请求条件筛选、查询所有的弹性云服务器，并关联获取弹性云服务器的详细信息。"),
        ("修改云服务器", "PUT", "https://{endpoint}/v1/{project_id}/cloudservers/{server_id}", "修改云服务器信息，目前支持修改云服务器名称和描述。"),
        ("变更云服务器规格", "POST", "https://{endpoint}/v1.1/{project_id}/cloudservers/{server_id}/resize", "变更云服务器规格。"),
        ("查询任务的执行状态", "GET", "https://{endpoint}/v1/{project_id}/jobs/{job_id}", "查询一个异步请求任务（Job）的执行状态。"),
        ("批量启动云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/action", "根据给定的云服务器ID列表，批量启动云服务器，1分钟内最多可以处理1000台。"),
        ("批量关闭云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/action", "根据给定的云服务器ID列表，批量关闭云服务器，1分钟内最多可以处理1000台。"),
        ("批量重启云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/action", "根据给定的云服务器ID列表，批量重启云服务器，1分钟内最多可以处理1000台。"),
        ("创建子网", "POST", "https://{endpoint}/v1/{project_id}/subnets", "创建子网。")
    ]

    uri_parameters_data = [
        # (api_name, parameter, mandatory, type, description)
        ("创建云服务器", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("创建云服务器", "project_id", True, None, "项目ID获取方法请参见获取项目ID"),
        ("删除云服务器", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("删除云服务器", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("查询云服务器详情", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询云服务器详情", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("查询云服务器详情", "server_id", True, None, "云服务器ID。"),
        ("查询云服务器详情列表", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询云服务器详情列表", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("查询云服务器详情列表", "offset", False, "Integer", "页码。当前页面数，默认值为1，取值范围大于等于0。当取值为0时，系统默认返回第1页，与取值为1时相同。建议设置该参数大于等于1。"),
        ("查询云服务器详情列表", "flavor", False, "String", "云服务器规格ID。已上线的规格请参见《弹性云服务器产品介绍》的“实例规格”章节。"),
        ("查询云服务器详情列表", "name", False, "String", "云服务器名称，匹配规则为模糊匹配。支持特殊字符，例如，\".\" 匹配除换行符（\\n、\\r）之外的任何单个字符，相等于 [^\\n\\r]。"),
        ("查询云服务器详情列表", "status", False, "String", "云服务器状态。取值范围：ACTIVE、BUILD、ERROR、HARD_REBOOT、MIGRATING、REBOOT、REBUILD、RESIZE、REVERT_RESIZE、SHUTOFF、VERIFY_RESIZE、DELETED、SHELVED、SHELVED_OFFLOADED 、UNKNOWN弹性云服务器状态说明请参考云服务器状态说明：当云服务器处于中间状态时，查询范围如下：ACTIVE，查询范围：ACTIVE，REBOOT，HARD_REBOOT，REBUILD，MIGRATING、RESIZESHUTOFF，查询范围：SHUTOFF，RESIZE，REBUILDERROR，查询范围：ERROR，REBUILDVERIFY_RESIZE，查询范围：VERIFY_RESIZE，REVERT_RESIZE"),
        ("查询云服务器详情列表", "limit", False, "Integer", "查询返回云服务器列表当前页面的数量。每页默认值是25，最多返回1000台云服务器的信息，如果数据量过大建议设置成100。"),
        ("查询云服务器详情列表", "tags", False, "String", "查询tag字段中包含该值的云服务器。"),
        ("查询云服务器详情列表", "not-tags", False, "String", "查询tag字段中不包含该值的云服务器。示例：查询的云服务器列表中不包含裸金属服务器，该字段设置如下：not-tags=__type_baremetal"),
        ("查询云服务器详情列表", "reservation_id", False, "String", "使用Openstack Nova 接口批量创建弹性云服务器时，会返回该ID，用于查询本次批量创建的弹性云服务器。"),
        ("查询云服务器详情列表", "enterprise_project_id", False, "String", "查询绑定某个企业项目的弹性云服务器。若需要查询当前用户所有企业项目绑定的弹性云服务器，请传参all_granted_eps。说明：查询的企业项目需具备ecs:cloudServers:list的权限。如果用户只有某个企业项目的权限，则需要传递该参数，查询指定企业项目绑定的弹性云服务器，否则会因权限不足而报错。当前all_granted_eps支持查询的企业项目个数不超过100。"),
        ("查询云服务器详情列表", "ip", False, "String", "IPv4地址过滤结果，匹配规则为模糊匹配。此处IP为云服务器的私有IP。"),
        ("查询云服务器详情列表", "ip_eq", False, "String", "IPv4地址过滤结果，匹配规则为精确匹配。此处IP为云服务器的私有IP。"),
        ("查询云服务器详情列表", "server_id", False, "String", "云服务器ID，格式为UUID，匹配规则为精确匹配示例：server_id={id1}&server_id={id2}说明：在使用server_id作为过滤条件时，不能同时使用其他过滤条件。如果同时指定server_id及其他过滤条件，则以server_id条件为准，其他过滤条件会被忽略当server_id中含有不存在的云服务器ID时，返回的响应参数中该云服务器ID对应的servers结构体中除了id和fault其它字段均为null为了避免API的URI过长，建议一次查询的server_id个数不超过100个"),
        ("修改云服务器", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("修改云服务器", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("修改云服务器", "server_id", True, None, "云服务器ID。"),
        ("变更云服务器规格", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("变更云服务器规格", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("变更云服务器规格", "server_id", True, None, "云服务器ID。云服务器的ID可以从控制台或者参考“查询云服务器列表”的章节获取。"),
        ("查询任务的执行状态", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询任务的执行状态", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("查询任务的执行状态", "job_id", True, None, "异步请求的任务ID。"),
        ("批量启动云服务器", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("批量启动云服务器", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("批量关闭云服务器", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("批量关闭云服务器", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("批量重启云服务器", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("批量重启云服务器", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("创建子网", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("创建子网", "project_id", True, None, "项目ID，获取项目ID请参见获取项目ID。"),
    ]

    request_parameters_data = [
        # (api_name, table_id, parameter, mandatory, type, description)
        ("创建云服务器", 1, "server", True, "Object", "弹性云服务器信息，请参见表2。"),
        ("创建云服务器", 1, "dry_run", False, "Boolean", "是否只预检此次请求，默认为false。true：发送检查请求，不会创建实例。检查项包括是否填写了必需参数、请求格式等。如果检查不通过，则返回对应错误。如果检查通过，则返回202状态码。false：发送正常请求，通过检查后并且执行创建云服务器请求。"),
        ("创建云服务器", 2, "imageRef", True, "String", "待创建云服务器的系统镜像，需要指定已创建镜像的ID，ID格式为通用唯一识别码（Universally Unique Identifier，简称UUID）。镜像的ID可以从控制台或者参考《镜像服务API参考》的“查询镜像列表”的章节获取。"),
        ("创建云服务器", 2, "flavorRef", True, "String", "待创建云服务器的系统规格的ID。已上线的规格请参见《弹性云服务器产品介绍》的“实例类型与规格”章节。"),
        ("创建云服务器", 2, "name", True, "String", "云服务器名称。创建的云服务器数量（count字段对应的值）大于1时，可以使用“自动排序”和“正则排序”设置有序的云服务器名称。请参考创建多台云服务器云主机时怎样设置有序的云服务器云主机名称？取值范围：只能由中文字符、英文字母、数字及“_”、“-”、“.”组成，且长度为[1-128]个英文字符或[1-64]个中文字符。创建的云服务器数量（count字段对应的值）大于1时，为区分不同云服务器，创建过程中系统会自动在名称后加“-0000”的类似标记。若用户在名称后已指定“-0000”的类似标记，系统将从该标记后继续顺序递增编号。故此时名称的长度为[1-59]个字符。说明：弹性云服务器内部主机名(hostname)命名规则遵循RFC 952和RFC 1123命名规范，建议使用a-z或0-9以及中划线\"-\"组成的名称命名，\"_\"将在弹性云服务器内部默认转化为\"-\"。"),
        ("创建云服务器", 2, "user_data", False, "String", "创建云服务器过程中待注入实例自定义数据。支持注入文本、文本文件。说明：user_data的值为base64编码之后的内容。注入内容（编码之前的内容）最大长度为32K。更多关于待注入实例自定义数据的信息，请参见《弹性云服务器用户指南 》的“用户数据注入”章节。示例：base64编码前：Linux服务器：#!/bin/bash echo user_test > /home/user.txtWindows服务器：rem cmd echo 111 > c:\aaa.txtbase64编码后：Linux服务器：IyEvYmluL2Jhc2gKZWNobyB1c2VyX3Rlc3QgPiAvaG9tZS91c2VyLnR4dA==Windows服务器：cmVtIGNtZAplY2hvIDExMSA+IGM6XGFhYS50eHQ="),
        ("创建云服务器", 2, "adminPass", False, "String", "如果需要使用密码方式登录云服务器，可使用adminPass字段指定云服务器管理员账户初始登录密码。其中，Linux管理员账户为root，Windows管理员账户为Administrator。密码复杂度要求：长度为8-26位。密码至少必须包含大写字母、小写字母、数字和特殊字符（!@$%^-_=+[{}]:,./?）中的三种。密码不能包含用户名或用户名的逆序。Windows系统密码不能包含用户名或用户名的逆序，不能包含用户名中超过两个连续字符的部分。"),
        ("创建云服务器", 2, "key_name", False, "String", "如果需要使用SSH密钥方式登录云服务器，请指定已创建密钥的名称。密钥可以通过密钥创建接口进行创建（请参见创建和导入SSH密钥），或使用SSH密钥查询接口查询已有的密钥（请参见查询SSH密钥列表）。约束：当创建云服务器的extendparam字段中chargingMode为prePaid时（即包年包月的弹性云服务器），key_name参数必须配合metadata字段使用。详情请参见创建云服务器的metadata字段数据结构说明，以及请求示例1。"),
        ("创建云服务器", 2, "vpcid", True, "String", "待创建云服务器所属虚拟私有云（简称VPC），需要指定已创建VPC的ID，UUID格式。VPC的ID可以从控制台或者参考《虚拟私有云接口参考》的“查询VPC”章节获取。"),
        ("创建云服务器", 2, "nics", True, "Array of objects", "待创建云服务器的网卡信息，包括子网ID。详情请参见表3"),
        ("创建云服务器", 2, "publicip", False, "Object", "配置云服务器的弹性IP信息，弹性IP有三种配置方式。不使用（无该字段）自动分配，需要指定新创建弹性IP的信息使用已有，需要指定已创建弹性IP的信息详情请参见publicip字段数据结构说明"),
        ("创建云服务器", 2, "count", False, "Integer", "创建云服务器数量。约束：不传该字段时默认取值为1。当extendparam结构中的chargingMode为postPaid（即创建按需付费的云服务器），且租户的配额足够时，最大值为500。当extendparam结构中的chargingMode为prePaid（即创建包年包月付费的云服务器）时，该值取值范围为[1，100]。但一次订购不要超过400个资源（比如购买一个弹性云服务器，至少包含了1个云主机、1个系统盘，有可能还包含数据盘、弹性IP、带宽多个资源，这些都属于资源，会算到400个内），超过400个资源时报错。"),
        ("创建云服务器", 2, "isAutoRename", False, "Boolean", "批量创建时是否使用相同的名称。默认为False，当count大于1的时候该参数生效。True，表示使用相同名称。False，表示自动增加后缀。"),
        ("创建云服务器", 2, "root_volume", True, "Object", "云服务器对应系统盘相关配置。创建包年/包月的弹性云服务器的时候，创建的系统盘/数据盘也是包年/包月，周期和弹性云服务器一致详情请参见表5"),
        ("创建云服务器", 2, "data_volumes", False, "Array of objects", "云服务器对应数据盘相关配置。每一个数据结构代表一块待创建的数据盘，可以选择不创建。详情请参见表6"),
        ("创建云服务器", 2, "security_groups", False, "Array of objects", "云服务器对应安全组信息。可以为空，此时默认给云服务器绑定default安全组。"),
        ("创建云服务器", 2, "availability_zone", False, "String", "待创建云服务器所在的可用区，需要指定可用分区名称。说明：如果为空，会自动指定一个符合要求的可用区。可通过接口查询可用区列表获取，也可参考地区和终端节点获取。"),
        ("创建云服务器", 2, "batch_create_in_multi_az", False, "Boolean", "是否支持随机多AZ部署，默认为false。true：批量创建的ecs部署在多个AZ上false：批量创建的ecs部署在单个AZ上当availability_zone为空时该字段生效。"),
        ("创建云服务器", 2, "extendparam", False, "Object", "创建云服务器附加信息。详情请参见表9"),
        ("创建云服务器", 2, "metadata", False, "Map<String,String>", "创建云服务器元数据。可以通过元数据自定义键值对。说明：如果元数据中包含了敏感数据，您应当采取适当的措施来保护敏感数据，比如限制访问范围、加密等。最多可注入10对键值（Key/Value）。主键（Key）只能由大写字母（A-Z）、小写字母（a-z）、数字（0-9）、中划线（-）、下划线（_）、冒号（:）、空格（ ）和小数点（.）组成，长度为[1-255]个字符。值（value）最大长度为255个字符。系统预留键值对请参见表11。"),
        ("创建云服务器", 2, "os:scheduler_hints", False, "Object", "云服务器调度信息，例如设置云服务器组。详情请参见表12。"),
        ("创建云服务器", 2, "tags", False, "Array of strings", "弹性云服务器的标签。标签的格式为“key.value”。其中，key的长度不超过36个字符，value的长度不超过43个字符。标签命名时，需满足如下要求：标签的key值只能包含大写字母（A~Z）、小写字母（a~z）、数字（0-9）、下划线（_）、中划线（-）以及中文字符。标签的value值只能包含大写字母（A~Z）、小写字母（a~z）、数字（0-9）、下划线（_）、中划线（-）、小数点（.）以及中文字符。说明：创建弹性云服务器时，一台弹性云服务器最多可以添加10个标签。云服务新增server_tags字段，该字段与tags字段功能相同，支持的key、value取值范围更广，建议使用server_tags字段。"),
        ("创建云服务器", 2, "server_tags", False, "Array of objects", "弹性云服务器的标签。详情请参见server_tags字段数据结构说明说明：创建弹性云服务器时，一台弹性云服务器最多可以添加10个标签。云服务新增server_tags字段，该字段与tags字段功能相同，支持的key、value取值范围更广，建议使用server_tags字段。"),
        ("创建云服务器", 2, "description", False, "String", "云服务器描述信息，默认为空字符串。长度最多允许85个字符。不能包含“<” 和 “>”。"),
        ("创建云服务器", 2, "auto_terminate_time", False, "String", "定时删除时间。按照ISO8601标准表示，并使用UTC +0时间，格式为yyyy-MM-ddTHH:mm:ssZ。如果秒（ss）取值不是 00，则自动取为当前分钟（mm）开始时。最短定时删除时间为当前时间半小时之后。最长定时删除时间不能超过当前时间三年。示例：2020-09-25T12:05:00Z说明：仅按需实例支持设置定时删除时间。该字段当前仅在华北-北京四、华南-广州区域生效。"),
        ("创建云服务器", 2, "cpu_options", False, "Object", "自定义CPU选项。详情请参见表7。"),
        ("创建云服务器", 3, "subnet_id", True, "String", "待创建云服务器所在的子网信息。需要指定vpcid对应VPC下已创建的子网（subnet）的网络ID，UUID格式。可以通过VPC服务查询子网列表接口查询。"),
        ("创建云服务器", 3, "ip_address", False, "String", "待创建云服务器网卡的IP地址，IPv4格式。约束：不填或空字符串，默认在子网（subnet）中自动分配一个未使用的IP作网卡的IP地址。若指定IP地址，该IP地址必须在子网（subnet）对应的网段内，且未被使用。"),
        ("创建云服务器", 3, "ipv6_enable", False, "Boolean", "是否支持ipv6。取值为true时，表示此网卡支持ipv6。"),
        ("创建云服务器", 3, "ipv6_bandwidth", False, "Object", "绑定的共享带宽信息，详情请参见ipv6_bandwidth字段数据结构说明。"),
        ("创建云服务器", 3, "allowed_address_pairs", False, "Array of allow_address_pair objects", "IP/Mac对列表，详情请参见表4(扩展属性)。约束：IP地址不允许为 “0.0.0.0/0”如果allowed_address_pairs配置地址池较大的CIDR（掩码小于24位），建议为该port配置一个单独的安全组如果allowed_address_pairs为“1.1.1.1/0”，表示关闭源目地址检查开关如果是虚拟IP绑定云服务器，则mac_address可为空或者填写被绑定云服务器网卡的Mac地址。被绑定的云服务器网卡allowed_address_pairs的IP地址填“1.1.1.1/0”。"),
        ("创建云服务器", 4, "ip_address", False, "String", "IP地址。约束：不支持0.0.0.0/0如果allowed_address_pairs配置地址池较大的CIDR（掩码小于24位），建议为该port配置一个单独的安全组。"),
        ("创建云服务器", 4, "mac_address", False, "String", "MAC地址。"),
        ("创建云服务器", 5, "volumetype", True, "String", "云服务器系统盘对应的磁盘类型，需要与系统所提供的磁盘类型相匹配。目前支持“SATA”，“SAS”，“GPSSD”，“SSD”，“ESSD”，“GPSSD2”和“ESSD2”。“SATA”为普通IO云硬盘（已售罄）“SAS”为高IO云硬盘“GPSSD”为通用型SSD云硬盘“SSD”为超高IO云硬盘“ESSD”为极速IO云硬盘“GPSSD2”为通用型SSD V2云硬盘“ESSD2”为极速型SSD V2云硬盘当指定的云硬盘类型在availability_zone内不存在时，则创建云硬盘失败。说明：了解不同磁盘类型的详细信息，请参见磁盘类型及性能介绍。"),
        ("创建云服务器", 5, "size", False, "Integer", "系统盘大小，容量单位为GB，输入大小范围为[1,1024]。约束：系统盘大小取值应不小于镜像支持的系统盘的最小值(镜像的min_disk属性)。若该参数没有指定或者指定为0时，系统盘大小默认取值为镜像中系统盘的最小值(镜像的min_disk属性)。说明：镜像系统盘的最小值（镜像的min_disk属性）可在控制台上单击镜像详情查看。或通过调用“查询镜像详情（OpenStack原生）”API获取，详细操作请参考《镜像服务API参考》中“查询镜像详情（OpenStack原生）”章节。"),
        ("创建云服务器", 5, "extendparam", False, "Object", "磁盘的产品信息。详情请参见创建磁盘的extendparam字段数据结构说明。"),
        ("创建云服务器", 5, "cluster_type", False, "String", "云服务器系统盘对应的磁盘存储类型。磁盘存储类型枚举值：DSS（专属存储类型）该参数需要与“cluster_id”配合使用，仅当“cluster_id”不为空时，才可以成功创建专属存储类型的磁盘。"),
        ("创建云服务器", 5, "cluster_id", False, "String", "云服务器系统盘对应的存储池的ID。"),
        ("创建云服务器", 5, "hw:passthrough", False, "Boolean", "设置云硬盘的设备类型：参数指定为false，创建VBD类型磁盘。参数指定为true，创建SCSI类型磁盘。参数未指定或者指定非Boolean类型的字符，默认创建VBD类型磁盘。说明：非QingTian规格仅支持设置系统盘为VBD类型。"),
        ("创建云服务器", 5, "metadata", False, "Object", "创建云硬盘的metadata信息，metadata中的key和value长度不大于255个字节。仅在创建加密盘时使用metadata字段。详情请参见创建磁盘的metadata字段数据结构说明"),
        ("创建云服务器", 5, "iops", False, "Integer", "为云硬盘配置iops。当“volumetype”设置为GPSSD2、ESSD2类型的云硬盘时，该参数必填，其他类型无需设置。说明：了解GPSSD2、ESSD2类型云硬盘的iops，请参见磁盘类型及性能介绍。仅支持按需计费。"),
        ("创建云服务器", 5, "throughput", False, "Integer", "为云硬盘配置吞吐量，单位是MiB/s。当“volumetype”设置为GPSSD2类型的云硬盘时必填，其他类型不能设置。说明：了解GPSSD2类型云硬盘的吞吐量大小范围，请参见磁盘类型及性能介绍。仅支持按需计费。"),
        ("创建云服务器", 6, "volumetype", True, "String", "云服务器数据盘对应的磁盘类型，需要与系统所提供的磁盘类型相匹配。目前支持“SATA”，“SAS”，“GPSSD”，“SSD”，“ESSD”，“GPSSD2”和“ESSD2”。“SATA”为普通IO云硬盘（已售罄）“SAS”为高IO云硬盘“GPSSD”为通用型SSD云硬盘“SSD”为超高IO云硬盘“ESSD”为极速IO云硬盘“GPSSD2”为通用型SSD V2云硬盘“ESSD2”为极速型SSD V2云硬盘当指定的云硬盘类型在availability_zone内不存在时，则创建云硬盘失败。说明：了解不同磁盘类型的详细信息，请参见磁盘类型及性能介绍。"),
        ("创建云服务器", 6, "size", True, "Integer", "数据盘大小，容量单位为GB，输入大小范围为[10,32768]。如果使用数据盘镜像创建数据盘时，size取值不能小于创建数据盘镜像的源数据盘的大小。"),
        ("创建云服务器", 6, "shareable", False, "Boolean", "是否为共享磁盘。true为共享盘，false为普通云硬盘。说明：该字段已废弃，请使用multiattach。"),
        ("创建云服务器", 6, "multiattach", False, "Boolean", "创建共享磁盘的信息。true：创建的磁盘为共享盘。false：创建的磁盘为普通云硬盘。说明：shareable当前为废弃字段，如果确实需要同时使用shareable字段和multiattach字段，此时，请确保两个字段的参数值相同。当不指定该字段时，系统默认创建普通云硬盘。"),
        ("创建云服务器", 6, "hw:passthrough", False, "Boolean", "设置云硬盘的设备类型：参数指定为false，创建VBD类型磁盘。参数指定为true，创建SCSI类型磁盘。参数未指定或者指定非Boolean类型的字符，默认创建VBD类型磁盘。说明：非QingTian规格仅支持设置系统盘为VBD类型。"),
        ("创建云服务器", 6, "extendparam", False, "Object", "磁盘的产品信息。详情请参见表7。"),
        ("创建云服务器", 6, "cluster_type", False, "String", "云服务器数据盘对应的磁盘存储类型。磁盘存储类型枚举值：DSS（专属存储类型）该参数需要与“cluster_id”配合使用，仅当“cluster_id”不为空时，才可以成功创建专属存储类型的磁盘。"),
        ("创建云服务器", 6, "cluster_id", False, "String", "云服务器数据盘对应的存储池的ID。"),
        ("创建云服务器", 6, "data_image_id", False, "String", "数据镜像的ID，UUID格式。如果使用数据盘镜像创建数据盘，则data_image_id为必选参数，且不支持使用metadata。"),
        ("创建云服务器", 6, "metadata", False, "Object", "创建云硬盘的metadata信息，metadata中的key和value长度不大于255个字节。仅在创建加密盘时使用metadata字段。如果使用数据盘镜像创建数据盘，不支持使用metadata。详情请参见创建磁盘的metadata字段数据结构说明"),
        ("创建云服务器", 6, "delete_on_termination", False, "Boolean", "数据盘随实例释放策略true：数据盘随实例释放。false：数据盘不随实例释放。默认值：false说明：该字段仅按需、竞价实例支持。"),
        ("创建云服务器", 6, "iops", False, "Integer", "为云硬盘配置iops。当“volumetype”设置为GPSSD2、ESSD2类型的云硬盘时，该参数必填，其他类型无需设置。说明：了解GPSSD2、ESSD2类型云硬盘的iops，请参见磁盘类型及性能介绍。仅支持按需计费。"),
        ("创建云服务器", 6, "throughput", False, "Integer", "为云硬盘配置吞吐量，单位是MiB/s。当“volumetype”设置为GPSSD2类型的云硬盘时必填，其他类型不能设置。说明：了解GPSSD2类型云硬盘的吞吐量大小范围，请参见磁盘类型及性能介绍。仅支持按需计费。"),
        ("创建云服务器", 7, "hw:cpu_threads", False, "integer", "CPU超线程数， 决定CPU是否开启超线程。取值范围：1，2。1: 关闭超线程。2: 打开超线程。需要同时满足如下条件，才能设置为“关闭超线程”：只能在实例创建或者resize时指定。只有目标flavor的extra_specs参数：存在“hw:cpu_policy”并取值为“dedicated”。存在“hw:cpu_threads”并取值为“2”。"),
        ("删除云服务器", 1, "servers", True, "Array of objects", "所需要删除的云服务器列表，详情请参见表3。"),
        ("删除云服务器", 1, "delete_publicip", False, "Boolean", "配置删除云服务器是否删除云服务器绑定的弹性公网IP。如果选择不删除，则系统仅做解绑定操作，保留弹性公网IP资源。取值为true或false。true：删除云服务器时，无论挂载在云服务器上的弹性公网IP的delete_on_termination字段为true或false，都会同时删除该弹性公网IP。false：删除云服务器时，无论挂载在云服务器上的弹性公网IP的delete_on_termination字段为true或false，仅做解绑操作，不删除该弹性公网IP。说明：若未设置delete_publicip参数，弹性公网IP是否随实例释放依赖于该弹性公网IP的delete_on_termination字段。delete_on_termination为true，delete_public为null，该弹性公网IP会被删除。delete_on_termination为false，delete_public为null，该弹性公网IP仅做解绑操作，不会被删除。"),
        ("删除云服务器", 1, "delete_volume", False, "Boolean", "配置删除云服务器是否删除云服务器对应的数据盘，如果选择不删除，则系统仅做卸载操作，保留云硬盘资源。默认为false。true：删除云服务器时会同时删除挂载在云服务器上的数据盘。false：删除云服务器时，仅卸载云服务器上挂载的数据盘，不删除该数据盘。"),
        ("删除云服务器", 3, "id", True, "String", "需要删除的云服务器ID。"),
        ("修改云服务器", 1, "server", True, "Object", "云服务器数据结构。详情请参见表3。"),
        ("修改云服务器", 3, "name", False, "String", "修改后的云服务器名称。只能由中文字符、英文字母、数字及“_”、“-”、“.”组成，且长度为[1-128]个英文字符或[1-64]个中文字符。"),
        ("修改云服务器", 3, "description", False, "String", "对弹性云服务器的任意描述。不能包含“<”,“>”，且长度范围为[0-85]个字符。"),
        ("修改云服务器", 3, "hostname", False, "String", "修改云服务器的hostname。命令规范：长度为 [1-64] 个字符，允许使用点号(.)分隔字符成多段，每段允许使用大小写字母、数字或连字符(-)，但不能连续使用点号(.)或连字符(-),不能以点号(.)或连字符(-)开头或结尾，不能出现（.-）和（-.）。说明：该字段已废弃，如需修改云服务器的hostname，请参考怎样使修改的静态主机名永久生效？。"),
        ("修改云服务器", 3, "user_data", False, "String", "修改云服务器过程中待注入实例自定义数据。支持注入文本、文本文件。说明：user_data的值为base64编码之后的内容。注入内容（编码之前的内容）最大长度为32K。更多关于待注入实例自定义数据的信息，请参见《弹性云服务器用户指南 》的“用户数据注入”章节。示例：base64编码前：Linux服务器：#!/bin/bash echo user_test > /home/user.txtWindows服务器：rem cmd echo 111 > c:\aaa.txtbase64编码后：Linux服务器：IyEvYmluL2Jhc2gKZWNobyB1c2VyX3Rlc3QgPiAvaG9tZS91c2VyLnR4dA==Windows服务器：cmVtIGNtZA0KZWNobyAxMTEgJmd0OyBjOlxhYWEudHh0"),
        ("变更云服务器规格", 1, "resize", True, "Object", "标记为云服务器变更规格操作，详情参见表3。"),
        ("变更云服务器规格", 1, "dry_run", False, "Boolean", "是否只预检此次请求。true：发送检查请求，不会变更云服务器规格。检查项包括是否填写了必需参数、请求格式等。如果检查不通过，则返回对应错误。如果检查通过，则返回202状态码。false：发送正常请求，通过检查后并且执行变更云服务器规格请求。"),
        ("变更云服务器规格", 3, "flavorRef", True, "String", "变更后的云服务器规格ID。可以通过查询云服务器规格变更支持列表接口查询允许变更的规格列表。说明：不支持变更至同一规格。"),
        ("变更云服务器规格", 3, "dedicated_host_id", False, "String", "新专属主机ID。仅对于部署在专属主机上的弹性云服务器，该参数必选。"),
        ("变更云服务器规格", 3, "extendparam", False, "Object", "变更云服务器扩展信息，详情参见表4。"),
        ("变更云服务器规格", 3, "mode", False, "String", "取值为withStopServer ，支持开机状态下变更规格。mode取值为withStopServer时，对开机状态的云服务器执行变更规格操作，系统自动对云服务器先执行关机，再变更规格，变更成功后再执行开机。"),
        ("变更云服务器规格", 3, "cpu_options", False, "Object", "自定义CPU选项。详情请参见表5。"),
        ("变更云服务器规格", 4, "isAutoPay", False, "String", "下单订购后，是否自动从客户的账户中支付，而不需要客户手动去进行支付。“true”：是（自动支付）“false”：否（需要客户手动支付）说明：当弹性云服务器是按包年包月计费时生效，该值为空时默认为客户手动支付。"),
        ("变更云服务器规格", 5, "hw:cpu_threads", False, "integer", "CPU超线程数， 决定CPU是否开启超线程。取值范围：1，2。1: 关闭超线程。2: 打开超线程。需要同时满足如下条件，才能设置为“关闭超线程”：只能在实例创建或者resize时指定。只有目标flavor的extra_specs参数：存在“hw:cpu_policy”并取值为“dedicated”。存在“hw:cpu_threads”并取值为“2”。"),
        ("批量启动云服务器", 1, "os-start", True, "Object", "标记为启动云服务器操作，详情请参见表3。"),
        ("批量启动云服务器", 3, "servers", True, "Array of objects", "云服务器ID列表，详情请参见表4。"),
        ("批量启动云服务器", 4, "id", True, "String", "云服务器ID。"),
        ("批量关闭云服务器", 1, "os-stop", True, "Object", "标记为关闭云服务器操作，详情请参见表3。"),
        ("批量关闭云服务器", 3, "servers", True, "Array of objects", "云服务器ID列表，详情请参见表4。"),
        ("批量关闭云服务器", 3, "type", False, "String", "关机类型，默认为SOFT：SOFT：普通关机（默认）。HARD：强制关机。"),
        ("批量关闭云服务器", 4, "id", True, "String", "云服务器ID。"),
        ("批量重启云服务器", 1, "reboot", True, "Object", "标记为重启云服务器操作，详情请参见表3。"),
        ("批量重启云服务器", 3, "type", True, "String", "重启类型：SOFT：普通重启。HARD：强制重启。"),
        ("批量重启云服务器", 3, "servers", True, "Array of objects", "云服务器ID列表，详情请参见表4。"),
        ("批量重启云服务器", 4, "id", True, "String", "云服务器ID。"),
        ("创建子网", 1, "subnet", True, "subnet object", "subnet对象，见表3"),
        ("创建子网", 3, "name", True, "String", "功能说明：子网名称取值范围：1-64个字符，支持数字、字母、中文、_(下划线)、-（中划线）、.（点）"),
        ("创建子网", 3, "description", False, "String", "功能说明：子网描述取值范围：0-255个字符，不能包含“<”和“>”。"),
        ("创建子网", 3, "cidr", True, "String", "功能说明：子网的网段取值范围：必须在vpc对应cidr范围内约束：必须是cidr格式。掩码长度不能大于28"),
        ("创建子网", 3, "gateway_ip", True, "String", "功能说明：子网的网关取值范围：子网网段中的IP地址约束：必须是ip格式"),
        ("创建子网", 3, "ipv6_enable", False, "Boolean", "功能说明：是否创建IPv6子网取值范围：true（开启），false（关闭）约束：不填时默认为false"),
        ("创建子网", 3, "dhcp_enable", False, "Boolean", "功能说明：子网是否开启dhcp功能取值范围：true（开启），false（关闭）约束：不填时默认为true。当设置为false时，会导致新创建的ECS无法获取IP地址，Cloud-init无法注入帐号密码，请谨慎操作。"),
        ("创建子网", 3, "primary_dns", False, "String", "功能说明：子网dns服务器地址1约束：ip格式，不支持IPv6地址。不填时，默认为空内网DNS地址请参见华为云提供的内网DNS地址是多少？可以通过查询名称服务器列表查看DNS服务器的地址。"),
        ("创建子网", 3, "secondary_dns", False, "String", "功能说明：子网dns服务器地址2约束：ip格式，不支持IPv6地址。不填时，默认为空内网DNS地址请参见华为云提供的内网DNS地址是多少？可以通过查询名称服务器列表查看DNS服务器的地址。"),
        ("创建子网", 3, "dnsList", False, "Array of strings", "功能说明：子网dns服务器地址的集合；如果想使用两个以上dns服务器，请使用该字段约束：是子网dns服务器地址1跟子网dns服务器地址2的合集的父集，不支持IPv6地址。不填时，默认为空内网DNS地址请参见华为云提供的内网DNS地址是多少？可以通过查询名称服务器列表查看DNS服务器的地址。"),
        ("创建子网", 3, "availability_zone", False, "String", "功能说明：子网所在的可用区标识，从终端节点获取，参考终端节点（Endpoint）约束：系统存在的可用区标识；不填时，默认为空"),
        ("创建子网", 3, "vpc_id", True, "String", "子网所在VPC标识"),
        ("创建子网", 3, "extra_dhcp_opts", False, "Array of extra_dhcp_opt objects", "子网配置的NTP地址或租约时间，详情请参见表4。"),
        ("创建子网", 4, "opt_value", False, "String", "功能说明：子网配置的NTP地址或子网配置的租约到期时间。约束：opt_name配置为“ntp”，则表示是子网ntp地址，目前只支持IPv4地址，每个IP地址以逗号隔开，IP地址个数不能超过4个，不能存在相同地址。该字段为null表示取消该子网NTP的设置，不能为“ ”(空字符串)。opt_name配置为“addresstime”，则该值表示是子网租约到期时间，取值格式有两种，取-1，表示无限租约；数字+h，数字范围是1~30000，比如5h。"),
        ("创建子网", 4, "opt_name", True, "String", "功能说明：子网配置的NTP地址名称或子网配置的租约到期名称。约束：目前只支持填写字符串“ntp”或“addresstime”。"),
    ]

    cursor.executemany('''
        INSERT INTO api_info (name, method, uri, description)
        VALUES (?, ?, ?, ?)''', api_info_data)
    
    cursor.executemany('''
        INSERT INTO uri_parameters (api_name, parameter, mandatory, type, description)
        VALUES (?, ?, ?, ?, ?)''', uri_parameters_data)

    cursor.executemany('''
        INSERT INTO request_parameters (api_name, table_id, parameter, mandatory, type, description)
        VALUES (?, ?, ?, ?, ?, ?)''', request_parameters_data)
    
    conn.commit()
    conn.close()
    return

def main():
    init_api_database()
    insert_data()
    return

if __name__ == "__main__":
    main()
