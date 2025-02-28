import pandas as pd
import sqlite3
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
API_DATABASE_FILE = os.path.join(current_dir, "api.sqlite")

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

    cursor.execute('DROP TABLE IF EXISTS apis;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            method TEXT NOT NULL,
            uri TEXT NOT NULL,
            description TEXT,
            root_table_id INTEGER NOT NULL,
            doc_page TEXT
        )''')
    
    cursor.execute("DROP TABLE IF EXISTS tables;")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tables (
            api_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL,
            caption TEXT,
            anchor_id TEXT,
            PRIMARY KEY (api_id, table_id)
        )''')
    
    cursor.execute('DROP TABLE IF EXISTS uri_parameters;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uri_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_id INTEGER NOT NULL,
            parameter TEXT NOT NULL,
            mandatory BOOLEAN NOT NULL,
            type TEXT,
            description TEXT
        )''')
    
    cursor.execute('DROP TABLE IF EXISTS request_parameters;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL,
            parameter TEXT NOT NULL,
            mandatory BOOLEAN NOT NULL,
            type TEXT,
            description TEXT,
            ref_table_id INTEGER
        )''')
    
    conn.commit()
    conn.close()
    return

def insert_data():
    conn = sqlite3.connect(API_DATABASE_FILE)
    cursor = conn.cursor()

    apis_data = [
        # (name, method, uri, description, root_table_id, doc_page)
        ("创建云服务器", "POST", "https://{endpoint}/v1.1/{project_id}/cloudservers", "创建一台或多台云服务器。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0101.html"),
        ("删除云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/delete", "根据指定的云服务器ID列表，删除云服务器。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0103.html"),
        ("查询云服务器详情", "GET", "https://{endpoint}/v1/{project_id}/cloudservers/{server_id}", "查询弹性云服务器的详细信息。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0104.html"),
        ("查询云服务器详情列表", "GET", "https://{endpoint}/v1/{project_id}/cloudservers/detail?flavor={flavor}&name={name}&status={status}&limit={limit}&offset={offset}&not-tags={not-tags}&reservation_id={reservation_id}&enterprise_project_id={enterprise_project_id}&tags={tags}&ip={ip}", "根据用户请求条件筛选、查询所有的弹性云服务器，并关联获取弹性云服务器的详细信息。", 1, "https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html"),
        ("修改云服务器", "PUT", "https://{endpoint}/v1/{project_id}/cloudservers/{server_id}", "修改云服务器信息，目前支持修改云服务器名称和描述。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0106.html"),
        ("变更云服务器规格", "POST", "https://{endpoint}/v1.1/{project_id}/cloudservers/{server_id}/resize", "变更云服务器规格。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0209.html"),
        ("查询任务的执行状态", "GET", "https://{endpoint}/v1/{project_id}/jobs/{job_id}", "查询一个异步请求任务（Job）的执行状态。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0901.html"),
        ("批量启动云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/action", "根据给定的云服务器ID列表，批量启动云服务器，1分钟内最多可以处理1000台。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0301.html"),
        ("批量关闭云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/action", "根据给定的云服务器ID列表，批量关闭云服务器，1分钟内最多可以处理1000台。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0303.html"),
        ("批量重启云服务器", "POST", "https://{endpoint}/v1/{project_id}/cloudservers/action", "根据给定的云服务器ID列表，批量重启云服务器，1分钟内最多可以处理1000台。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_0302.html"),
        ("创建子网", "POST", "https://{endpoint}/v1/{project_id}/subnets", "创建子网。", 1, "https://support.huaweicloud.com/api-vpc/vpc_subnet01_0001.html"),
        ("查询规格详情和规格扩展信息列表", "GET", "https://{endpoint}/v1/{project_id}/cloudservers/flavors?availability_zone={availability_zone}", "查询云服务器规格详情信息和规格扩展信息列表。", 1, "https://support.huaweicloud.com/api-ecs/zh-cn_topic_0020212656.html"),
        ("创建VPC", "POST", "https://{endpoint}/v1/{project_id}/vpcs", "创建虚拟私有云。", 1, "https://support.huaweicloud.com/api-vpc/vpc_api01_0001.html"),
        ("查询镜像列表", "GET", "https://{endpoint}/v2/cloudimages{?__isregistered,__imagetype,__whole_image,__system__cmkid,protected,visibility,owner,id,status,name,flavor_id,container_format,disk_format,min_ram,min_disk,__os_bit,__platform,marker,limit,sort_key,sort_dir,__os_type,tag,member_status,__support_kvm,__support_xen,__support_largememory,__support_diskintensive,__support_highperformance,__support_xen_gpu_type,__support_kvm_gpu_type,__support_xen_hana,__support_kvm_infiniband,virtual_env_type,enterprise_project_id,created_at,updated_at,architecture}", "根据不同条件查询镜像列表信息。", 1, "https://support.huaweicloud.com/api-ims/ims_03_0602.html"),
        ("地域推荐", "POST", "https://{endpoint}/v1/{domain_id}/recommendations/ecs-supply", "对ECS的资源供给的地域和规格进行推荐，推荐结果以打分的形式呈现，分数越高推荐程度越高。", 1, "https://support.huaweicloud.com/api-ecs/ecs_02_1901.html"),
        ("查询VPC列表", "GET", "https://{endpoint}/v1/{project_id}/vpcs", "查询虚拟私有云列表。", 1, "https://support.huaweicloud.com/api-vpc/vpc_api01_0003.html"),
        ("查询子网列表", "GET", "https://{endpoint}/v1/{project_id}/subnets", "查询子网列表。", 1, "https://support.huaweicloud.com/api-vpc/vpc_subnet01_0003.html"),
        ("查询安全组列表", "GET", "https://{endpoint}/v1/{project_id}/security-groups", "查询安全组列表。", 1, "https://support.huaweicloud.com/api-vpc/vpc_sg01_0003.html"),
        ("创建安全组", "POST", "https://{endpoint}/v1/{project_id}/security-groups", "创建安全组。", 1, "https://support.huaweicloud.com/api-vpc/vpc_sg01_0001.html"),
        ('创建集群', 'POST', 'https://{endpoint}/api/v3/projects/{project_id}/clusters', '#### 功能介绍\n该API用于创建一个空集群（即只有控制节点Master，没有工作节点Node）。请在调用本接口完成集群创建之后，通过创建节点添加节点。\n- 集群管理的URL格式为：https://Endpoint/uri。其中uri为资源路径，也即API访问的路径。\n- 调用该接口创建集群时，默认不安装ICAgent，若需安装ICAgent，可在请求Body参数的annotations中加入"cluster.install.addons.external/install":"[{"addonTemplateName":"icagent"}]"的集群注解，将在创建集群时自动安装ICAgent。ICAgent是应用性能管理APM的采集代理，运行在应用所在的服务器上，用于实时采集探针所获取的数据，安装ICAgent是使用应用性能管理APM的前提。', 3, 'https://support.huaweicloud.com/api-cce/cce_02_0236.html'),
    ]

    uri_parameters_data = [
        # (api_name, parameter, mandatory, type, description)
        ("创建云服务器", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("创建云服务器", "project_id", True, None, "项目ID 获取方法请参见获取项目ID"),
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
        ("查询规格详情和规格扩展信息列表", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询规格详情和规格扩展信息列表", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("查询规格详情和规格扩展信息列表", "availability_zone", False, "String", "可用区，需要指定可用区（AZ）的名称，当此字段不为空时，只返回可使用（如：normal、obt、promotion等状态）的flavor列表。请参考地区和终端节点获取。"),
        ("创建VPC", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("创建VPC", "project_id", True, None, "项目ID。获取方法请参见获取项目ID。"),
        ("查询镜像列表", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询镜像列表", "__isregistered", False, "String", "镜像是否可用，取值为true，扩展接口会默认为true，普通用户只能查询取值为true的镜像。"),
        ("查询镜像列表", "__imagetype", False, "String", "镜像类型，目前支持以下类型： 公共镜像：gold 私有镜像：private 共享镜像：shared 市场镜像：market 说明： 当前租户共享给其他租户的私有镜像或当前租户接受的共享镜像中，__imagetype均为shared，可用owner字段进行区分。当前租户接受的共享镜像可用member_status进行过滤查询。"),
        ("查询镜像列表", "__whole_image", False, "Boolean", "是否为整机镜像，取值为true/false。"),
        ("查询镜像列表", "__system__cmkid", False, "String", "加密镜像所使用的密钥ID。可以从镜像服务控制台获取，或者调用查询镜像列表API查询。"),
        ("查询镜像列表", "protected", False, "Boolean", "镜像是否是受保护，取值为true/false，一般查询公共镜像时候取值为true，查询私有镜像可以不指定。"),
        ("查询镜像列表", "visibility", False, "String", "是否被其他租户可见，取值如下： public：公共镜像 private：私有镜像 shared：共享镜像"),
        ("查询镜像列表", "owner", False, "String", "镜像属于哪个租户。"),
        ("查询镜像列表", "id", False, "String", "镜像ID。"),
        ("查询镜像列表", "status", False, "String", "镜像状态。取值如下： queued：表示镜像元数据已经创建成功，等待上传镜像文件。 saving：表示镜像正在上传文件到后端存储。 deleted：表示镜像已经删除。 killed：表示镜像上传错误。 active：表示镜像可以正常使用。"),
        ("查询镜像列表", "name", False, "String", "镜像名称，匹配规则为精确匹配。name参数说明请参考镜像属性。"),
        ("查询镜像列表", "flavor_id", False, "String", "用于通过云服务器规格过滤出可用公共镜像，取值为规格ID。 约束： 仅支持通过单个规格进行过滤。 仅支持按照云服务器规格进行过滤，裸金属服务器暂不支持。 如果需要查看某裸金属服务器规格支持的公共镜像，可以使用“__support_s4l=true”标签。其中，s4l为裸金属服务器规格的board_type，若规格为“physical.s4.large”，则填入“s4l”。详细说明请参见“怎么确定裸金属服务器规格的board_type？”。调用示例请参考常用列表查询方法。"),
        ("查询镜像列表", "container_format", False, "String", "容器类型，取值为bare。"),
        ("查询镜像列表", "disk_format", False, "String", "镜像格式，目前支持zvhd2、vhd、zvhd、raw、qcow2、iso。非iso格式时默认值是zvhd2。"),
        ("查询镜像列表", "min_ram", False, "Integer", "镜像运行需要的最小内存，单位为MB。参数取值依据云服务器的规格限制，一般设置为0。 云服务器的规格限制，请参见规格清单。"),
        ("查询镜像列表", "min_disk", False, "Integer", "镜像运行需要的最小磁盘，单位为GB 。linux操作系统取值为10～1024GB，Windows操作系统取值为20～1024GB。"),
        ("查询镜像列表", "__os_bit", False, "String", "操作系统位数，一般取值为32或者64。"),
        ("查询镜像列表", "__platform", False, "String", "镜像平台分类，取值为Windows、Ubuntu、Red Hat、SUSE、CentOS、Debian、OpenSUSE、Oracle Linux、Fedora、Other、CoreOS、EulerOS和Huawei Cloud EulerOS等。"),
        ("查询镜像列表", "marker", False, "String", "用于分页，表示从哪个镜像开始查询，取值为镜像ID。"),
        ("查询镜像列表", "limit", False, "Integer", "用于分页，表示查询几条镜像记录，取值为整数，默认取值为500。"),
        ("查询镜像列表", "sort_key", False, "String", "用于排序，表示按照哪个字段排序。取值为镜像属性name、container_format、disk_format、status、id、size、created_at字段，默认为创建时间。"),
        ("查询镜像列表", "sort_dir", False, "String", "用于排序，表示升序还是降序，取值为asc和desc。与sort_key一起组合使用，默认为降序desc。"),
        ("查询镜像列表", "__os_type", False, "String", "镜像系统类型，取值如下： Linux Windows Other"),
        ("查询镜像列表", "tag", False, "String", "标签，用户为镜像增加自定义标签后可以通过该参数过滤查询。 说明： 系统近期对标签功能进行了升级。如果之前添加的Tag为“Key.Value”的形式，则查询的时候需要使用“Key=Value”的格式来查询。例如：之前添加的tag为“a.b”,则升级后，查询时需使用“tag=a=b”。"),
        ("查询镜像列表", "member_status", False, "String", "成员状态。目前取值有accepted、rejected、pending。accepted表示已经接受共享的镜像，rejected表示已经拒绝了其他用户共享的镜像，pending表示需要确认的其他用户的共享镜像。需要在查询时，设置“visibility”参数为“shared”。"),
        ("查询镜像列表", "__support_kvm", False, "String", "如果镜像支持KVM，取值为true，否则无需增加该属性。"),
        ("查询镜像列表", "__support_xen", False, "String", "如果镜像支持XEN，取值为true，否则无需增加该属性。"),
        ("查询镜像列表", "__support_largememory", False, "String", "表示该镜像支持超大内存。如果镜像支持超大内存，取值为true，否则无需增加该属性。 镜像操作系统类型请参考“弹性云服务器类型与支持的操作系统版本”。"),
        ("查询镜像列表", "__support_diskintensive", False, "String", "表示该镜像支持密集存储。如果镜像支持密集存储性能，则值为true，否则无需增加该属性。"),
        ("查询镜像列表", "__support_highperformance", False, "String", "表示该镜像支持高计算性能。如果镜像支持高计算性能，则值为true，否则无需增加该属性。"),
        ("查询镜像列表", "__support_xen_gpu_type", False, "String", "表示该镜像是支持XEN虚拟化平台下的GPU优化类型，取值参考表2。如果不支持XEN虚拟化下GPU类型，无需添加该属性。该属性与“__support_xen”和“__support_kvm”属性不共存。"),
        ("查询镜像列表", "__support_kvm_gpu_type", False, "String", "表示该镜像是支持KVM虚拟化平台下的GPU类型，取值参考表3。如果不支持KVM虚拟化下GPU类型，无需添加该属性。该属性与“__support_xen”和“__support_kvm”属性不共存。"),
        ("查询镜像列表", "__support_xen_hana", False, "String", "如果镜像支持XEN虚拟化下HANA类型，取值为true。否则，无需添加该属性。 该属性与“__support_xen”和“__support_kvm”属性不共存。"),
        ("查询镜像列表", "__support_kvm_infiniband", False, "String", "如果镜像支持KVM虚拟化下Infiniband网卡类型，取值为true。否则，无需添加该属性。 该属性与“__support_xen”属性不共存。"),
        ("查询镜像列表", "virtual_env_type", False, "String", "镜像使用环境类型：FusionCompute、Ironic、DataImage、IsoImage。 如果是云服务器镜像（即系统盘镜像），则取值为FusionCompute。 如果是数据盘镜像，则取值是DataImage。 如果是裸金属服务器镜像，则取值是Ironic。 如果是ISO镜像，则取值是IsoImage。"),
        ("查询镜像列表", "enterprise_project_id", False, "String", "表示查询某个企业项目下的镜像。 取值为0，表示查询属于default企业项目下的镜像。 取值为UUID，表示查询属于该UUID对应的企业项目下的镜像。 取值为all_granted_eps，表示查询当前用户所有企业项目下的镜像。 关于企业项目ID的获取及企业项目特性的详细信息，请参考“企业中心总览”。"),
        ("查询镜像列表", "created_at", False, "String", "镜像创建时间。支持按照时间点过滤查询，取值格式为“操作符:UTC时间”。 其中操作符支持如下几种： gt：大于 gte：大于等于 lt：小于 lte：小于等于 eq：等于 neq：不等于 时间格式支持：yyyy-MM-ddThh:mm:ssZ或者yyyy-MM-dd hh:mm:ss 例如，查询创建时间在2018-10-28 10:00:00之前的镜像，可以通过如下条件过滤： created_at=lt:2018-10-28T10:00:00Z"),
        ("查询镜像列表", "updated_at", False, "String", "镜像修改时间。支持按照时间点过滤查询，取值格式为“操作符:UTC时间”。 其中操作符支持如下几种： gt：大于 gte：大于等于 lt：小于 lte：小于等于 eq：等于 neq：不等于 时间格式支持：yyyy-MM-ddThh:mm:ssZ或者yyyy-MM-dd hh:mm:ss 例如，查询修改时间在2018-10-28 10:00:00之前的镜像，可以通过如下条件过滤： updated_at=lt:2018-10-28T10:00:00Z"),
        ("查询镜像列表", "architecture", False, "String", "镜像架构类型。取值包括： x86 arm"),
        ("地域推荐", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("地域推荐", "domain_id", True, None, "租户域ID。"),
        ("查询VPC列表", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询VPC列表", "project_id", True, "String", "项目ID，获取项目ID请参见获取项目ID。"),
        ("查询VPC列表", "id", False, "String", "按照VPC ID过滤查询。"),
        ("查询VPC列表", "marker", False, "String", "分页查询的起始资源ID，表示从指定资源的下一条记录开始查询。 marker需要和limit配合使用： 若不传入marker和limit参数，查询结果返回第一页全部资源记录。 若不传入marker参数，limit为10，查询结果返回第1~10条资源记录。 若marker为第10条记录的资源ID，limit为10，查询结果返回第11~20条资源记录。 若marker为第10条记录的资源ID，不传入limit参数，查询结果返回第11~2000条（limit默认值2000）资源记录。"),
        ("查询VPC列表", "limit", False, "Integer", "分页查询每页返回的记录个数，取值范围为0~intmax（2^31-1），默认值2000。 limit需要和marker配合使用，详细规则请见marker的参数说明。"),
        ("查询VPC列表", "enterprise_project_id", False, "String", "功能说明：按照企业项目ID过滤查询，可以使用该字段过滤某个企业项目下的虚拟私有云。 取值范围：最大长度36字节，带“-”连字符的UUID格式，或者是字符串“0”。“0”表示默认企业项目。若需要查询当前用户所有企业项目绑定的虚拟私有云，请传参all_granted_eps。"),
        ("查询子网列表", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询子网列表", "project_id", True, "String", "项目ID，获取项目ID请参见获取项目ID。"),
        ("查询子网列表", "marker", False, "String", "分页查询的起始资源ID，表示从指定资源的下一条记录开始查询。 marker需要和limit配合使用： 若不传入marker和limit参数，查询结果返回第一页全部资源记录。 若不传入marker参数，limit为10，查询结果返回第1~10条资源记录。 若marker为第10条记录的资源ID，limit为10，查询结果返回第11~20条资源记录。 若marker为第10条记录的资源ID，不传入limit参数，查询结果返回第11~2000条（limit默认值2000）资源记录。"),
        ("查询子网列表", "limit", False, "Integer", "分页查询每页返回的记录个数，取值范围为0~intmax（2^31-1），默认值2000。 limit需要和marker配合使用，详细规则请见marker的参数说明。"),
        ("查询子网列表", "vpc_id", False, "String", "按照子网所在VPC ID过滤查询。 企业项目细粒度授权场景下，该字段必传。"),
        ("查询安全组列表", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("查询安全组列表", "project_id", True, "String", "项目ID，获取项目ID请参见获取项目ID。"),
        ("查询安全组列表", "marker", False, "String", "分页查询的起始资源ID，表示从指定资源的下一条记录开始查询。 marker需要和limit配合使用： 若不传入marker和limit参数，查询结果返回第一页全部资源记录。 若不传入marker参数，limit为10，查询结果返回第1~10条资源记录。 若marker为第10条记录的资源ID，limit为10，查询结果返回第11~20条资源记录。 若marker为第10条记录的资源ID，不传入limit参数，查询结果返回第11~2000条（limit默认值2000）资源记录。"),
        ("查询安全组列表", "limit", False, "Integer", "分页查询每页返回的记录个数，取值范围为0~intmax（2^31-1），默认值2000。 limit需要和marker配合使用，详细规则请见marker的参数说明。"),
        ("查询安全组列表", "vpc_id", False, "String", "按照vpc_id过滤查询。"),
        ("查询安全组列表", "enterprise_project_id", False, "String", "功能说明：企业项目ID。可以使用该字段过滤某个企业项目下的安全组。 取值范围：最大长度36字节，带“-”连字符的UUID格式，或者是字符串“0”。“0”表示默认企业项目。若需要查询当前用户所有企业项目绑定的安全组，或者企业项目子账号需要进行安全组列表展示，请传参all_granted_eps。 说明： 关于企业项目ID的获取及企业项目特性的详细信息，请参见《企业管理用户指南》。"),
        ("查询安全组列表", "remote_address_group_id", False, "String", "功能说明：远端IP地址组ID。您可以登录管理控制台，在IP地址组页面查看该ID。 约束：和remote_ip_prefix，remote_group_id功能互斥。"),
        ("创建安全组", "endpoint", True, None, "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"),
        ("创建安全组", "project_id", True, None, "项目ID，获取项目ID请参见获取项目ID。"),
        ('创建集群', 'endpoint', True, 'String', '指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。\n例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。'),
        ('创建集群', 'project_id', True, 'String', '**参数解释：**\n项目ID，获取方式请参见如何获取接口URI中参数。\n**约束限制：**\n不涉及\n**取值范围：**\n账号的项目ID\n**默认取值：**\n不涉及'),
    ]

    request_parameters_data = [
        # (api_name, table_id, parameter, mandatory, type, description, ref_table_id)
        ("创建云服务器", 1, "server", True, "Object", "弹性云服务器信息，请参见表2。", 2),
        ("创建云服务器", 1, "dry_run", False, "Boolean", "是否只预检此次请求，默认为false。 true：发送检查请求，不会创建实例。检查项包括是否填写了必需参数、请求格式等。 如果检查不通过，则返回对应错误。 如果检查通过，则返回202状态码。 false：发送正常请求，通过检查后并且执行创建云服务器请求。", None),
        ("创建云服务器", 2, "imageRef", True, "String", "待创建云服务器的系统镜像，需要指定已创建镜像的ID，ID格式为通用唯一识别码（Universally Unique Identifier，简称UUID）。 镜像的ID可以从控制台或者参考《镜像服务API参考》的“查询镜像列表”的章节获取。", None),
        ("创建云服务器", 2, "flavorRef", True, "String", "待创建云服务器的系统规格的ID。 已上线的规格请参见《弹性云服务器产品介绍》的“实例类型与规格”章节。", None),
        ("创建云服务器", 2, "name", True, "String", "云服务器名称。 创建的云服务器数量（count字段对应的值）大于1时，可以使用“自动排序”和“正则排序”设置有序的云服务器名称。 请参考创建多台云服务器云主机时怎样设置有序的云服务器云主机名称？ 取值范围： 只能由中文字符、英文字母、数字及“_”、“-”、“.”组成，且长度为[1-128]个英文字符或[1-64]个中文字符。 创建的云服务器数量（count字段对应的值）大于1时，为区分不同云服务器，创建过程中系统会自动在名称后加“-0000”的类似标记。若用户在名称后已指定“-0000”的类似标记，系统将从该标记后继续顺序递增编号。故此时名称的长度为[1-59]个字符。 说明： 弹性云服务器内部主机名(hostname)命名规则遵循RFC 952和RFC 1123命名规范，建议使用a-z或0-9以及中划线\"-\"组成的名称命名，\"_\"将在弹性云服务器内部默认转化为\"-\"。", None),
        ("创建云服务器", 2, "user_data", False, "String", "创建云服务器过程中待注入实例自定义数据。支持注入文本、文本文件。 说明： user_data的值为base64编码之后的内容。 注入内容（编码之前的内容）最大长度为32K。 更多关于待注入实例自定义数据的信息，请参见《弹性云服务器用户指南 》的“用户数据注入”章节。 示例： base64编码前： Linux服务器： #!/bin/bash echo user_test > /home/user.txt Windows服务器： rem cmd echo 111 > c:\aaa.txt base64编码后： Linux服务器： IyEvYmluL2Jhc2gKZWNobyB1c2VyX3Rlc3QgPiAvaG9tZS91c2VyLnR4dA== Windows服务器： cmVtIGNtZAplY2hvIDExMSA+IGM6XGFhYS50eHQ=", None),
        ("创建云服务器", 2, "adminPass", False, "String", "如果需要使用密码方式登录云服务器，可使用adminPass字段指定云服务器管理员账户初始登录密码。其中，Linux管理员账户为root，Windows管理员账户为Administrator。 密码复杂度要求： 长度为8-26位。 密码至少必须包含大写字母、小写字母、数字和特殊字符（!@$%^-_=+[{}]:,./?）中的三种。 密码不能包含用户名或用户名的逆序。 Windows系统密码不能包含用户名或用户名的逆序，不能包含用户名中超过两个连续字符的部分。", None),
        ("创建云服务器", 2, "key_name", False, "String", "如果需要使用SSH密钥方式登录云服务器，请指定已创建密钥的名称。 密钥可以通过密钥创建接口进行创建（请参见创建和导入SSH密钥对），或使用SSH密钥查询接口查询已有的密钥（请参见查询SSH密钥对列表）。", None),
        ("创建云服务器", 2, "vpcid", True, "String", "待创建云服务器所属虚拟私有云（简称VPC），需要指定已创建VPC的ID，UUID格式。 VPC的ID可以从控制台或者参考《虚拟私有云接口参考》的“查询VPC”章节获取。", None),
        ("创建云服务器", 2, "nics", True, "Array of objects", "待创建云服务器的网卡信息。详情请参见表3 约束： 主网卡对应的网络（network）必须属于vpcid对应的VPC。用户创建网卡时，指定的第一张网卡信息为主网卡。 当前单个弹性云服务器默认支持最多挂载12张网卡。 不同的规格对网卡上限有一定的区别，参考规格清单。", 3),
        ("创建云服务器", 2, "publicip", False, "Object", "配置云服务器的弹性IP信息，弹性IP有三种配置方式。 不使用（无该字段） 自动分配，需要指定新创建弹性IP的信息 使用已有，需要指定已创建弹性IP的信息 详情请参见publicip字段数据结构说明（表101）", 101),
        ("创建云服务器", 2, "count", False, "Integer", "创建云服务器数量。 约束： 不传该字段时默认取值为1。 当extendparam结构中的chargingMode为postPaid（即创建按需付费的云服务器），且租户的配额足够时，最大值为500。 当extendparam结构中的chargingMode为prePaid（即创建包年包月付费的云服务器）时，该值取值范围为[1，100]。但一次订购不要超过400个资源（比如购买一个弹性云服务器，至少包含了1个云主机、1个系统盘，有可能还包含数据盘、弹性IP、带宽多个资源，这些都属于资源，会算到400个内），超过400个资源时报错。", None),
        ("创建云服务器", 2, "isAutoRename", False, "Boolean", "批量创建时是否使用相同的名称。默认为False，当count大于1的时候该参数生效。 True，表示使用相同名称。 False，表示自动增加后缀。", None),
        ("创建云服务器", 2, "root_volume", True, "Object", "云服务器对应系统盘相关配置。 创建包年/包月的弹性云服务器的时候，创建的系统盘/数据盘也是包年/包月，周期和弹性云服务器一致 详情请参见表5", 5),
        ("创建云服务器", 2, "data_volumes", False, "Array of objects", "云服务器对应数据盘相关配置。每一个数据结构代表一块待创建的数据盘。 约束：目前弹性云服务器最多可挂载59块数据盘（部分规格只支持23块数据盘） 详情请参见表6", 6),
        ("创建云服务器", 2, "security_groups", False, "Array of objects", "云服务器对应安全组信息。 约束：当该值指定为空时，默认给云服务器绑定default安全组。 详情请参见security_groups字段数据结构说明（表102）", 102),
        ("创建云服务器", 2, "availability_zone", False, "String", "待创建云服务器所在的可用区，需要指定可用分区名称。 说明： 如果为空，会自动指定一个符合要求的可用区。 如果在专属主机上创建云服务器，需指定云服务器与专属主机所在可用区一致。 可通过接口 查询可用区列表（废弃） 获取，也可参考地区和终端节点获取。", None),
        ("创建云服务器", 2, "batch_create_in_multi_az", False, "Boolean", "是否支持随机多AZ部署，默认为false。 true：批量创建的ecs部署在多个AZ上 false：批量创建的ecs部署在单个AZ上 当availability_zone为空时该字段生效。", None),
        ("创建云服务器", 2, "extendparam", False, "Object", "创建云服务器附加信息。详情请参见表109", 109),
        ("创建云服务器", 2, "metadata", False, "Map<String,String>", "创建云服务器元数据。 可以通过元数据自定义键值对。 说明： 如果元数据中包含了敏感数据，您应当采取适当的措施来保护敏感数据，比如限制访问范围、加密等。 最多可注入10对键值（Key/Value）。 主键（Key）只能由大写字母（A-Z）、小写字母（a-z）、数字（0-9）、中划线（-）、下划线（_）、冒号（:）、空格（ ）和小数点（.）组成，长度为[1-255]个字符。 值（value）最大长度为255个字符。 系统预留键值对请参见表111。", 111),
        ("创建云服务器", 2, "os:scheduler_hints", False, "Object", "云服务器调度信息，例如设置云服务器组。 详情请参见表112。", 112),
        ("创建云服务器", 2, "tags", False, "Array of strings", "弹性云服务器的标签。 标签的格式为“key.value”。其中，key的长度不超过36个字符，value的长度不超过43个字符。 标签命名时，需满足如下要求： 标签的key值只能包含大写字母（A~Z）、小写字母（a~z）、数字（0-9）、下划线（_）、中划线（-）以及中文字符。 标签的value值只能包含大写字母（A~Z）、小写字母（a~z）、数字（0-9）、下划线（_）、中划线（-）、小数点（.）以及中文字符。 说明： 创建弹性云服务器时，一台弹性云服务器最多可以添加10个标签。 云服务新增server_tags字段，该字段与tags字段功能相同，支持的key、value取值范围更广，建议使用server_tags字段。", None),
        ("创建云服务器", 2, "server_tags", False, "Array of objects", "弹性云服务器的标签。详情请参见server_tags字段数据结构说明（表114） 说明： 创建弹性云服务器时，一台弹性云服务器最多可以添加10个标签。 云服务新增server_tags字段，该字段与tags字段功能相同，支持的key、value取值范围更广，建议使用server_tags字段。", 114),
        ("创建云服务器", 2, "description", False, "String", "云服务器描述信息，默认为空字符串。 长度最多允许85个字符。 不能包含“<” 和 “>”。", None),
        ("创建云服务器", 2, "auto_terminate_time", False, "String", "定时删除时间。 按照ISO8601标准表示，并使用UTC +0时间，格式为yyyy-MM-ddTHH:mm:ssZ。 如果秒（ss）取值不是 00，则自动取为当前分钟（mm）开始时。 最短定时删除时间为当前时间半小时之后。 最长定时删除时间不能超过当前时间三年。 示例：2020-09-25T12:05:00Z 说明： 仅按需实例支持设置定时删除时间。 该字段当前仅在华北-北京四、华南-广州区域生效。", None),
        ("创建云服务器", 2, "cpu_options", False, "Object", "自定义CPU选项。 详情请参见表7。", 7),
        ("创建云服务器", 3, "subnet_id", True, "String", "待创建云服务器所在的子网信息。 需要指定vpcid对应VPC下已创建的子网（subnet）的网络ID，UUID格式。 可以通过VPC服务查询子网列表接口查询。", None),
        ("创建云服务器", 3, "ip_address", False, "String", "待创建云服务器网卡的IP地址，IPv4格式。 约束： 不填或空字符串，默认在子网（subnet）中自动分配一个未使用的IP作网卡的IP地址。 若指定IP地址，该IP地址必须在子网（subnet）对应的网段内，且未被使用。", None),
        ("创建云服务器", 3, "ipv6_enable", False, "Boolean", "是否支持ipv6。取值为true时，表示此网卡支持ipv6。", None),
        ("创建云服务器", 3, "ipv6_bandwidth", False, "Object", "绑定的共享带宽信息，详情请参见ipv6_bandwidth字段数据结构说明（表105）。", 105),
        ("创建云服务器", 3, "allowed_address_pairs", False, "Array of allow_address_pair objects", "IP/Mac对列表，详情请参见表4(扩展属性)。 约束：IP地址不允许为 “0.0.0.0/0” 如果allowed_address_pairs配置地址池较大的CIDR（掩码小于24位），建议为该port配置一个单独的安全组 如果allowed_address_pairs为“1.1.1.1/0”，表示关闭源目地址检查开关 如果是虚拟IP绑定云服务器， 则mac_address可为空或者填写被绑定云服务器网卡的Mac地址。 被绑定的云服务器网卡allowed_address_pairs的IP地址填“1.1.1.1/0”。", 4),
        ("创建云服务器", 4, "ip_address", False, "String", "IP地址。 约束：不支持0.0.0.0/0 如果allowed_address_pairs配置地址池较大的CIDR（掩码小于24位），建议为该port配置一个单独的安全组。", None),
        ("创建云服务器", 4, "mac_address", False, "String", "MAC地址。", None),
        ("创建云服务器", 5, "volumetype", True, "String", "云服务器系统盘对应的磁盘类型，需要与系统所提供的磁盘类型相匹配。 目前支持“SATA”，“SAS”，“GPSSD”，“SSD”，“ESSD”，“GPSSD2”和“ESSD2”。 “SATA”为普通IO云硬盘（已售罄） “SAS”为高IO云硬盘 “GPSSD”为通用型SSD云硬盘 “SSD”为超高IO云硬盘 “ESSD”为极速IO云硬盘 “GPSSD2”为通用型SSD V2云硬盘 “ESSD2”为极速型SSD V2云硬盘 当指定的云硬盘类型在availability_zone内不存在时，则创建云硬盘失败。 说明： 了解不同磁盘类型的详细信息，请参见磁盘类型及性能介绍。", None),
        ("创建云服务器", 5, "size", False, "Integer", "系统盘大小，容量单位为GB，输入大小范围为[1,1024]。 约束： 系统盘大小取值应不小于镜像支持的系统盘的最小值(镜像的min_disk属性)。 若该参数没有指定或者指定为0时，系统盘大小默认取值为镜像中系统盘的最小值(镜像的min_disk属性)。 说明： 镜像系统盘的最小值（镜像的min_disk属性）可在控制台上单击镜像详情查看。或通过调用“查询镜像详情（OpenStack原生）”API获取，详细操作请参考《镜像服务API参考》中“查询镜像详情（OpenStack原生）”章节。", None),
        ("创建云服务器", 5, "extendparam", False, "Object", "磁盘的产品信息。 详情请参见创建磁盘的extendparam字段数据结构说明（表107）。", 107),
        ("创建云服务器", 5, "cluster_type", False, "String", "云服务器系统盘对应的磁盘存储类型。 磁盘存储类型枚举值：DSS（专属存储类型） 该参数需要与“cluster_id”配合使用，仅当“cluster_id”不为空时，才可以成功创建专属存储类型的磁盘。", None),
        ("创建云服务器", 5, "cluster_id", False, "String", "云服务器系统盘对应的存储池的ID。", None),
        ("创建云服务器", 5, "hw:passthrough", False, "Boolean", "设置云硬盘的设备类型： 参数指定为false，创建VBD类型磁盘。 参数指定为true，创建SCSI类型磁盘。 参数未指定或者指定非Boolean类型的字符，默认创建VBD类型磁盘。 说明： 非QingTian规格仅支持设置系统盘为VBD类型。", None),
        ("创建云服务器", 5, "metadata", False, "Object", "创建云硬盘的metadata信息，metadata中的key和value长度不大于255个字节。 仅在创建加密盘时使用metadata字段。 详情请参见创建磁盘的metadata字段数据结构说明（表110）", 110),
        ("创建云服务器", 5, "iops", False, "Integer", "为云硬盘配置iops。当“volumetype”设置为GPSSD2、ESSD2类型的云硬盘时，该参数必填，其他类型无需设置。 说明： 了解GPSSD2、ESSD2类型云硬盘的iops，请参见磁盘类型及性能介绍。 仅支持按需计费。", None),
        ("创建云服务器", 5, "throughput", False, "Integer", "为云硬盘配置吞吐量，单位是MiB/s。当“volumetype”设置为GPSSD2类型的云硬盘时必填，其他类型不能设置。 说明： 了解GPSSD2类型云硬盘的吞吐量大小范围，请参见磁盘类型及性能介绍。 仅支持按需计费。", None),
        ("创建云服务器", 6, "volumetype", True, "String", "云服务器数据盘对应的磁盘类型，需要与系统所提供的磁盘类型相匹配。 目前支持“SATA”，“SAS”，“GPSSD”，“SSD”，“ESSD”，“GPSSD2”和“ESSD2”。 “SATA”为普通IO云硬盘（已售罄） “SAS”为高IO云硬盘 “GPSSD”为通用型SSD云硬盘 “SSD”为超高IO云硬盘 “ESSD”为极速IO云硬盘 “GPSSD2”为通用型SSD V2云硬盘 “ESSD2”为极速型SSD V2云硬盘 当指定的云硬盘类型在availability_zone内不存在时，则创建云硬盘失败。 说明： 了解不同磁盘类型的详细信息，请参见磁盘类型及性能介绍。", None),
        ("创建云服务器", 6, "size", True, "Integer", "数据盘大小，容量单位为GB，输入大小范围为[10,32768]。 如果使用数据盘镜像创建数据盘时，size取值不能小于创建数据盘镜像的源数据盘的大小。", None),
        ("创建云服务器", 6, "shareable", False, "Boolean", "是否为共享磁盘。true为共享盘，false为普通云硬盘。 说明： 该字段已废弃，请使用multiattach。", None),
        ("创建云服务器", 6, "multiattach", False, "Boolean", "创建共享磁盘的信息。 true：创建的磁盘为共享盘。 false：创建的磁盘为普通云硬盘。 说明： shareable当前为废弃字段，如果确实需要同时使用shareable字段和multiattach字段，此时，请确保两个字段的参数值相同。当不指定该字段时，系统默认创建普通云硬盘。", None),
        ("创建云服务器", 6, "hw:passthrough", False, "Boolean", "设置云硬盘的设备类型： 参数指定为false，创建VBD类型磁盘。 参数指定为true，创建SCSI类型磁盘。 参数未指定或者指定非Boolean类型的字符，默认创建VBD类型磁盘。 说明： 非QingTian规格仅支持设置系统盘为VBD类型。", None),
        ("创建云服务器", 6, "extendparam", False, "Object", "磁盘的产品信息。 详情请参见表107。", 107),
        ("创建云服务器", 6, "cluster_type", False, "String", "云服务器数据盘对应的磁盘存储类型。 磁盘存储类型枚举值：DSS（专属存储类型） 该参数需要与“cluster_id”配合使用，仅当“cluster_id”不为空时，才可以成功创建专属存储类型的磁盘。", None),
        ("创建云服务器", 6, "cluster_id", False, "String", "云服务器数据盘对应的存储池的ID。", None),
        ("创建云服务器", 6, "data_image_id", False, "String", "数据镜像的ID，UUID格式。 如果使用数据盘镜像创建数据盘，则data_image_id为必选参数，且不支持使用metadata。", None),
        ("创建云服务器", 6, "metadata", False, "Object", "创建云硬盘的metadata信息，metadata中的key和value长度不大于255个字节。 仅在创建加密盘时使用metadata字段。 如果使用数据盘镜像创建数据盘，不支持使用metadata。 详情请参见创建磁盘的metadata字段数据结构说明（表110）", 110),
        ("创建云服务器", 6, "delete_on_termination", False, "Boolean", "数据盘随实例释放策略 true：数据盘随实例释放。 false：数据盘不随实例释放。 默认值：false 说明： 该字段仅按需、竞价实例支持。", None),
        ("创建云服务器", 6, "iops", False, "Integer", "为云硬盘配置iops。当“volumetype”设置为GPSSD2、ESSD2类型的云硬盘时，该参数必填，其他类型无需设置。 说明： 了解GPSSD2、ESSD2类型云硬盘的iops，请参见磁盘类型及性能介绍。 仅支持按需计费。", None),
        ("创建云服务器", 6, "throughput", False, "Integer", "为云硬盘配置吞吐量，单位是MiB/s。当“volumetype”设置为GPSSD2类型的云硬盘时必填，其他类型不能设置。 说明：了解GPSSD2类型云硬盘的吞吐量大小范围，请参见磁盘类型及性能介绍。 仅支持按需计费。", None),
        ("创建云服务器", 7, "hw:cpu_threads", False, "integer", "用于控制CPU是否开启超线程。 取值范围：1，2。 1: 关闭超线程。 2: 打开超线程。 需要同时满足如下条件，才能设置为“关闭超线程”： 只能在实例创建或者resize时指定。 只有目标flavor的extra_specs参数： 存在“hw:cpu_policy”并取值为“dedicated”。 存在“hw:cpu_threads”并取值为“2”。", None),
        ("创建云服务器", 101, "id", False, "String", "为待创建云服务器分配已有弹性公网IP时，分配的弹性公网IP的ID，UUID格式。 约束：只能分配状态（status）为DOWN的弹性公网IP。", None),
        ("创建云服务器", 101, "eip", False, "Object", "配置云服务器自动分配弹性公网IP时，创建弹性公网IP的配置参数。 详情请参见表103。", 103),
        ("创建云服务器", 101, "delete_on_termination", False, "Boolean", "弹性公网IP随实例释放策略。 true：弹性公网IP随实例释放。 false：弹性公网IP不随实例释放。 默认值：false。 说明： 该字段仅按需弹性公网IP支持。", None),
        ("创建云服务器", 102, "id", False, "String", "待创建云服务器的安全组，会对创建云服务器中配置的网卡生效。需要指定已有安全组的ID，UUID格式；若不传id字段，底层会创建默认安全组。", None),
        ("创建云服务器", 103, "iptype", True, "String", "弹性公网IP地址类型。 详情请参见“申请弹性公网IP”章节的“publicip”字段说明。", None),
        ("创建云服务器", 103, "bandwidth", True, "Object", "弹性公网IP地址带宽参数。 详情请参见bandwidth字段数据结构说明（表104）。", 104),
        ("创建云服务器", 103, "extendparam", False, "Object", "创建弹性公网IP的附加信息。 详情请参见表106 说明： 当创建云服务器的extendparam结构中chargingMode为prePaid时（即创建包年包月付费的云服务器），若需要创建按需计费的弹性IP，该字段必选，需要在该结构中增加chargingMode为postPaid（按需付费）。", 106),
        ("创建云服务器", 104, "size", False, "Integer", "功能说明：带宽大小 带宽（Mbit/s），取值范围为[1,2000]。 具体范围以各区域配置为准，请参见控制台对应页面显示。 调整带宽时的最小单位会根据带宽范围不同存在差异。 小于等于300Mbit/s：默认最小单位为1Mbit/s。 300Mbit/s~1000Mbit/s：默认最小单位为50Mbit/s。 大于1000Mbit/s：默认最小单位为500Mbit/s。 说明： 如果share_type是PER，该参数必选项；如果share_type是WHOLE并且id有值，该参数会忽略。", None),
        ("创建云服务器", 104, "sharetype", True, "String", "带宽的共享类型。 共享类型枚举：PER，表示独享。WHOLE，表示共享。", None),
        ("创建云服务器", 104, "chargemode", False, "String", "带宽的计费类型。 未传该字段，表示按带宽计费。 字段值为空，表示按带宽计费。 字段值为“traffic”，表示按流量计费。 字段为其它值，会导致创建云服务器失败。 说明： 如果share_type是WHOLE并且id有值，该参数会忽略。", None),
        ("创建云服务器", 104, "id", False, "String", "带宽ID，创建WHOLE类型带宽的弹性IP时可以指定之前的共享带宽创建。 取值范围：WHOLE类型的带宽ID。 说明： 当创建WHOLE类型的带宽时，该字段必选。", None),
        ("创建云服务器", 105, "id", False, "String", "IPv6带宽的ID。", None),
        ("创建云服务器", 106, "chargingMode", False, "String", "公网IP的计费模式。 取值范围： prePaid-预付费，即包年包月； postPaid-后付费，即按需付费； 说明： 如果bandwidth对象中share_type是WHOLE且id有值，弹性公网IP只能创建为按需付费的，故该参数传参“prePaid”无效。", None),
        ("创建云服务器", 107, "resourceSpecCode", False, "String", "磁盘产品资源规格编码，如SATA，SAS和SSD。 说明： 废弃字段。", None),
        ("创建云服务器", 107, "resourceType", False, "String", "磁盘产品资源类型。 说明： 废弃字段。", None),
        ("创建云服务器", 107, "snapshotId", False, "String", "整机镜像中自带的原始数据盘（简称“原数据盘”）所对应的快照ID或原始数据盘ID。 使用场景： 使用整机镜像创建云服务器，并且选择的整机镜像自带1个或者多个数据盘。 使用整机镜像创建云服务器时，系统会自动恢复整机镜像中自带的数据盘（包括数据盘类型和数据）。此时，您可以通过snapshotId，修改指定原数据盘恢复后的磁盘类型。 说明： 建议对每块原数据盘都指定snapshotId。 如需修改磁盘大小，修改后的磁盘大小需大于等于原数据盘大小。否则，会影响原数据盘的数据恢复。 如需设置磁盘共享，需指定共享属性。 如需设置磁盘加密，需在metadata字段指定相关加密属性。 实现原理： snapshotId是整机镜像自带原始数据盘的唯一标识，通过snapshotId可以获取原数据盘的磁盘信息，从而恢复数据盘数据。 通过管理控制台获取snapshotId： 登录管理控制台，打开\"云硬盘 > 快照\"页面，根据原始数据盘的磁盘名称找到对应的快照ID或者原始数据盘的ID。 通过API查询snapshotId： 已知整机镜像ID，参考镜像服务的“查询镜像详情”接口获取整机镜像ID关联的云备份或云服务器备份ID。 如果使用的是云备份，请使用云备份ID查询备份信息，响应信息children字段中包含的resource_id或snapshot_id即为所需的snapshotId。详细操作请参考云备份服务“查询指定备份”接口。 如果使用的是云服务器备份，请使用云服务器备份ID查询备份信息，响应信息volume_backups字段中包含的source_volume_id或snapshot_id即为所需的snapshotId。详细操作请参考云服务器备份“查询单个备份”接口。", None),
        ("创建云服务器", 108, "chargingMode", False, "Integer", "计费模式： 0：按需计费。(默认值是0)", None),
        ("创建云服务器", 108, "regionID", False, "String", "云服务器所在区域ID。 请参考地区和终端节点获取。", None),
        ("创建云服务器", 108, "support_auto_recovery", False, "Boolean", "是否配置云服务器自动恢复的功能。 “true”：配置该功能 “false”：不配置该功能 说明： 此参数为boolean类型，若传入非boolean类型字符，程序将按照“false”：不配置该功能的方式处理。 当support_auto_recovery=false,flavor中不存在\"cond:compute\": autorecovery：不支持自动恢复功能。 当support_auto_recovery=false,flavor中存在\"cond:compute\": autorecovery：仍支持自动恢复功能。 \"cond:compute\": autorecovery可通过查询规格详情和规格扩展信息列表查询。", None),
        ("创建云服务器", 108, "enterprise_project_id", False, "String", "企业项目ID。 说明： 关于企业项目ID的获取及企业项目特性的详细信息，请参见《企业管理服务用户指南》。 该字段不传（或传为字符串“0”），则将资源绑定给默认企业项目。", None),
        ("创建云服务器", 108, "marketType", False, "String", "创建竞价实例时，需指定该参数的值为“spot”。 说明： 当chargingMode=0时且marketType=spot时此参数生效。", None),
        ("创建云服务器", 108, "spotPrice", False, "String", "用户愿意为竞价实例每小时支付的最高价格。 说明： 仅chargingMode=0且marketType=spot时，该参数设置后生效。 当chargingMode=0且marketType=spot时，如果不传递spotPrice，默认使用按需购买的价格作为竞价。 spotPrice需要小于等于按需价格，并要大于等于云服务器市场价格。", None),
        ("创建云服务器", 108, "diskPrior", False, "String", "是否支持先创建卷，再创建虚拟机。 “true”：配置该功能 “false”：不配置该功能", None),
        ("创建云服务器", 108, "spot_duration_hours", False, "Integer", "购买的竞价实例时长。 说明： 竞享实例必传且当interruption_policy=immediate时，该字段有效 。 spot_duration_hours大于0。最大值由预测系统给出可以从flavor的extra_specs的cond:spot_block:operation:longest_duration_hours字段中查询。", None),
        ("创建云服务器", 108, "spot_duration_count", False, "Integer", "表示购买的“竞价实例时长”的个数。 说明： 适用于竞享实例且当spot_duration_hours>0时，该字段有效。 spot_duration_hours小于6时，spot_duration_count值必须为1。 spot_duration_hours等于6时，spot_duration_count大于等于1。 spot_duration_count的最大值由预测系统给出可以从flavor的extra_specs的cond:spot_block:operation:longest_duration_count字段中查询。", None),
        ("创建云服务器", 108, "interruption_policy", False, "String", "竞价实例中断策略，当前支持immediate（立即释放）。 说明： 当实例为竞享模式时，必须设置为immediate", None),
        ("创建云服务器", 108, "CB_CSBS_BACKUP", False, "String", "云备份策略和云备份存储库详情，取值包含备份策略ID和云备份存储库ID。 例如：在控制台查询备份策略ID为：fdcaa27d-5be4-4f61-afe3-09ff79162c04 云备份存储库ID为：332a9408-463f-436a-9e92-78dad95d1ac4 则CB_CSBS_BACKUP取值为：\"{\"policy_id\":\"fdcaa27d-5be4-4f61-afe3-09ff79162c04\",\"vault_id\":\"332a9408-463f-436a-9e92-78dad95d1ac4\"}\"", None),
        ("创建云服务器", 109, "chargingMode", False, "String", "计费模式。 功能说明：付费方式 取值范围： prePaid-预付费，即包年包月； postPaid-后付费，即按需付费； 默认值是postPaid 说明： 当chargingMode为prePaid（即创建包年包月付费的云服务器），且使用SSH密钥方式登录云服务器时，metadata中的op_svc_userid字段为必选字段。 metadata中的op_svc_userid字段的取值，请参见表111。", None),
        ("创建云服务器", 109, "regionID", False, "String", "云服务器所在区域ID。 请参考地区和终端节点获取。", None),
        ("创建云服务器", 109, "periodType", False, "String", "订购周期类型。 取值范围： month-月 year-年 说明： chargingMode为prePaid时生效且为必选值。", None),
        ("创建云服务器", 109, "periodNum", False, "Integer", "订购周期数。 取值范围： periodType=month（周期类型为月）时，取值为[1，2，3，4，5，6，7，8，9]； periodType=year（周期类型为年）时，取值为[1，2，3]； 说明：chargingMode为prePaid时生效且为必选值。 periodNum为正整数。 根据华为云ECS产品定价规则，1年ECS（包年）价格=10个月ECS（包月）价格，因此购买包月时长超过9个月时，可直接购买包年ECS产品。", None),
        ("创建云服务器", 109, "isAutoRenew", False, "String", "是否自动续订。 “true”：自动续订 “false”：不自动续订 说明： chargingMode为prePaid时生效，不传该字段时默认为不自动续订。", None),
        ("创建云服务器", 109, "isAutoPay", False, "String", "下单订购后，是否自动从客户的账户中支付，而不需要客户手动去进行支付。 “true”：是（自动支付） “false”：否（需要客户手动支付） 说明： chargingMode为prePaid时生效，不传该字段时默认为客户手动支付。", None),
        ("创建云服务器", 109, "enterprise_project_id", False, "String", "企业项目ID。 说明： 关于企业项目ID的获取及企业项目特性的详细信息，请参见《企业管理服务用户指南》。 该字段不传（或传为字符串“0”），则将资源绑定给默认企业项目。", None),
        ("创建云服务器", 109, "support_auto_recovery", False, "Boolean", "是否配置虚拟机自动恢复的功能。 “true”：配置该功能 “false”：不配置该功能 说明： 此参数为boolean类型，若传入非boolean类型字符，程序将按照【“false”：不配置该功能】方式处理。 当marketType为spot时，不支持该功能。", None),
        ("创建云服务器", 109, "marketType", False, "String", "创建竞价实例时，需指定该参数的值为“spot”。 说明： 当chargingMode=postPaid且marketType=spot时，此参数生效。", None),
        ("创建云服务器", 109, "spotPrice", False, "String", "用户愿意为竞价云服务器每小时支付的最高价格。 说明： 仅chargingMode=postPaid且marketType=spot时，该参数设置后生效。 当chargingMode=postPaid且marketType=spot时，如果不传递spotPrice或者传递一个空字符串，默认使用按需购买的价格作为竞价。 spotPrice需要小于等于按需价格，并要大于等于云服务器市场价格。", None),
        ("创建云服务器", 109, "diskPrior", False, "String", "是否支持先创建卷，再创建虚拟机。 “true”：配置该功能 “false”：不配置该功能", None),
        ("创建云服务器", 109, "spot_duration_hours", False, "Integer", "购买的竞价实例时长。 说明： 竞享实例必传且当interruption_policy=immediate时，该字段有效 。 spot_duration_hours大于0。最大值由预测系统给出可以从flavor的extra_specs的cond:spot_block:operation:longest_duration_hours字段中查询。", None),
        ("创建云服务器", 109, "spot_duration_count", False, "Integer", "表示购买的“竞价实例时长”的个数。 说明： 适用于竞享实例且当spot_duration_hours>0时，该字段有效。 spot_duration_hours小于6时，spot_duration_count值必须为1。 spot_duration_hours等于6时，spot_duration_count大于等于1。 spot_duration_count的最大值由预测系统给出可以从flavor的extra_specs的cond:spot_block:operation:longest_duration_count字段中查询。", None),
        ("创建云服务器", 109, "interruption_policy", False, "String", "竞价实例中断策略，当前支持immediate（立即释放）。 说明： 当实例为竞享模式时，必须设置为immediate", None),
        ("创建云服务器", 109, "CB_CSBS_BACKUP", False, "String", "云备份策略和云备份存储库详情，取值包含备份策略ID和云备份存储库ID。 例如：在控制台查询备份策略ID为：fdcaa27d-5be4-4f61-afe3-09ff79162c04 云备份存储库ID为：332a9408-463f-436a-9e92-78dad95d1ac4 则CB_CSBS_BACKUP取值为：\"{\"policy_id\":\"fdcaa27d-5be4-4f61-afe3-09ff79162c04\",\"vault_id\":\"332a9408-463f-436a-9e92-78dad95d1ac4\"}\"", None),
        ("创建云服务器", 110, "__system__encrypted", False, "String", "metadata中的表示加密功能的字段，0代表不加密，1代表加密。 该字段不存在时，云硬盘默认为不加密。", None),
        ("创建云服务器", 110, "__system__cmkid", False, "String", "用户主密钥ID，是metadata中的表示加密功能的字段，与__system__encrypted配合使用。 说明： 请参考查询密钥列表，通过HTTPS请求获取密钥ID。", None),
        ("创建云服务器", 111, "op_svc_userid", False, "String", "用户ID。 您可以在我的凭证下，通过“API凭证”页面的“IAM用户ID”，获取该参数的值。更多内容，请参见API凭证。 说明： 该参数取值为当前登录账号的“IAM用户ID”，如果您当前使用IAM用户登录，则需要获取对应IAM用户的“IAM用户ID”。", None),
        ("创建云服务器", 111, "agency_name", False, "String", "委托的名称。 委托是由租户管理员在统一身份认证服务（Identity and Access Management，IAM）上创建的，可以为弹性云服务器提供访问云服务的临时凭证。 说明： 委托获取、更新请参考如下步骤： 使用IAM服务提供的查询委托列表接口，获取有效可用的委托名称。 使用更新云服务器元数据接口，更新metadata中agency_name字段为新的委托名称。", None),
        ("创建云服务器", 111, "__support_agent_list", False, "String", "云服务器是否支持主机安全服务、主机监控。 \"ces\"：主机监控 \"hss\"：主机安全服务基础版 \"hss,hss-ent\"：主机安全服务企业版 取值样例： __support_agent_list:“hss,ces” 可以通过查询镜像详情判断创建云服务器使用的镜像是否支持主机安全服务或主机监控。", None),
        ("创建云服务器", 112, "group", False, "String", "云服务器组ID，UUID格式。 云服务器组的ID可以从控制台或者参考查询云服务器组列表获取。 说明： 请确保云服务器组使用的是反亲和性anti-affinity策略，不推荐使用其他策略。 在指定的专属主机上创建的弹性云服务器不支持选择反亲和性anti-affinity策略。", None),
        ("创建云服务器", 112, "tenancy", False, "String", "在指定的专属主机或者共享主机上创建弹性云服务器。 参数值为shared或者dedicated。", None),
        ("创建云服务器", 112, "dedicated_host_id", False, "String", "专属主机的ID。 说明： 专属主机的ID仅在tenancy为dedicated时生效。", None),
        ("创建云服务器", 114, "key", True, "String", "键。 最大长度36个unicode字符。key不能为空。不能包含非打印字符ASCII(0-31)，\"=\", \"*\",“<”,“>”,“\”,“,”,“|”,“/”。 同一资源的key值不能重复。", None),
        ("创建云服务器", 114, "value", True, "String", "值。 每个值最大长度43个unicode字符，可以为空字符串。 不能包含非打印字符ASCII(0-31)，“=”,“*”,“<”,“>”,“\”,“,”,“|”。", None),
        ("删除云服务器", 1, "servers", True, "Array of objects", "所需要删除的云服务器列表，详情请参见表3。", 3),
        ("删除云服务器", 1, "delete_publicip", False, "Boolean", "配置删除云服务器是否删除云服务器绑定的弹性公网IP。如果选择不删除，则系统仅做解绑定操作，保留弹性公网IP资源。取值为true或false。true：删除云服务器时，无论挂载在云服务器上的弹性公网IP的delete_on_termination字段为true或false，都会同时删除该弹性公网IP。false：删除云服务器时，无论挂载在云服务器上的弹性公网IP的delete_on_termination字段为true或false，仅做解绑操作，不删除该弹性公网IP。说明：若未设置delete_publicip参数，弹性公网IP是否随实例释放依赖于该弹性公网IP的delete_on_termination字段。delete_on_termination为true，delete_public为null，该弹性公网IP会被删除。delete_on_termination为false，delete_public为null，该弹性公网IP仅做解绑操作，不会被删除。", None),
        ("删除云服务器", 1, "delete_volume", False, "Boolean", "配置删除云服务器是否删除云服务器对应的数据盘，如果选择不删除，则系统仅做卸载操作，保留云硬盘资源。默认为false。true：删除云服务器时会同时删除挂载在云服务器上的数据盘。false：删除云服务器时，仅卸载云服务器上挂载的数据盘，不删除该数据盘。", None),
        ("删除云服务器", 3, "id", True, "String", "需要删除的云服务器ID。", None),
        ("修改云服务器", 1, "server", True, "Object", "云服务器数据结构。详情请参见表3。", 3),
        ("修改云服务器", 3, "name", False, "String", "修改后的云服务器名称。只能由中文字符、英文字母、数字及“_”、“-”、“.”组成，且长度为[1-128]个英文字符或[1-64]个中文字符。", None),
        ("修改云服务器", 3, "description", False, "String", "对弹性云服务器的任意描述。不能包含“<”,“>”，且长度范围为[0-85]个字符。", None),
        ("修改云服务器", 3, "hostname", False, "String", "修改云服务器的hostname。命令规范：长度为 [1-64] 个字符，允许使用点号(.)分隔字符成多段，每段允许使用大小写字母、数字或连字符(-)，但不能连续使用点号(.)或连字符(-),不能以点号(.)或连字符(-)开头或结尾，不能出现（.-）和（-.）。说明：该字段已废弃，如需修改云服务器的hostname，请参考怎样使修改的静态主机名永久生效？。", None),
        ("修改云服务器", 3, "user_data", False, "String", "修改云服务器过程中待注入实例自定义数据。支持注入文本、文本文件。说明：user_data的值为base64编码之后的内容。注入内容（编码之前的内容）最大长度为32K。更多关于待注入实例自定义数据的信息，请参见《弹性云服务器用户指南 》的“用户数据注入”章节。示例：base64编码前：Linux服务器：#!/bin/bash echo user_test > /home/user.txtWindows服务器：rem cmd echo 111 > c:\aaa.txtbase64编码后：Linux服务器：IyEvYmluL2Jhc2gKZWNobyB1c2VyX3Rlc3QgPiAvaG9tZS91c2VyLnR4dA==Windows服务器：cmVtIGNtZA0KZWNobyAxMTEgJmd0OyBjOlxhYWEudHh0", None),
        ("变更云服务器规格", 1, "resize", True, "Object", "标记为云服务器变更规格操作，详情参见表3。", 3),
        ("变更云服务器规格", 1, "dry_run", False, "Boolean", "是否只预检此次请求。true：发送检查请求，不会变更云服务器规格。检查项包括是否填写了必需参数、请求格式等。如果检查不通过，则返回对应错误。如果检查通过，则返回202状态码。false：发送正常请求，通过检查后并且执行变更云服务器规格请求。", None),
        ("变更云服务器规格", 3, "flavorRef", True, "String", "变更后的云服务器规格ID。可以通过查询云服务器规格变更支持列表接口查询允许变更的规格列表。说明：不支持变更至同一规格。", None),
        ("变更云服务器规格", 3, "dedicated_host_id", False, "String", "新专属主机ID。仅对于部署在专属主机上的弹性云服务器，该参数必选。", None),
        ("变更云服务器规格", 3, "extendparam", False, "Object", "变更云服务器扩展信息，详情参见表4。", 4),
        ("变更云服务器规格", 3, "mode", False, "String", "取值为withStopServer ，支持开机状态下变更规格。mode取值为withStopServer时，对开机状态的云服务器执行变更规格操作，系统自动对云服务器先执行关机，再变更规格，变更成功后再执行开机。", None),
        ("变更云服务器规格", 3, "cpu_options", False, "Object", "自定义CPU选项。详情请参见表5。", 5),
        ("变更云服务器规格", 4, "isAutoPay", False, "String", "下单订购后，是否自动从客户的账户中支付，而不需要客户手动去进行支付。“true”：是（自动支付）“false”：否（需要客户手动支付）说明：当弹性云服务器是按包年包月计费时生效，该值为空时默认为客户手动支付。", None),
        ("变更云服务器规格", 5, "hw:cpu_threads", False, "integer", "CPU超线程数， 决定CPU是否开启超线程。取值范围：1，2。1: 关闭超线程。2: 打开超线程。需要同时满足如下条件，才能设置为“关闭超线程”：只能在实例创建或者resize时指定。只有目标flavor的extra_specs参数：存在“hw:cpu_policy”并取值为“dedicated”。存在“hw:cpu_threads”并取值为“2”。", None),
        ("批量启动云服务器", 1, "os-start", True, "Object", "标记为启动云服务器操作，详情请参见表3。", 3),
        ("批量启动云服务器", 3, "servers", True, "Array of objects", "云服务器ID列表，详情请参见表4。", 4),
        ("批量启动云服务器", 4, "id", True, "String", "云服务器ID。", None),
        ("批量关闭云服务器", 1, "os-stop", True, "Object", "标记为关闭云服务器操作，详情请参见表3。", 3),
        ("批量关闭云服务器", 3, "servers", True, "Array of objects", "云服务器ID列表，详情请参见表4。", 4),
        ("批量关闭云服务器", 3, "type", False, "String", "关机类型，默认为SOFT：SOFT：普通关机（默认）。HARD：强制关机。", None),
        ("批量关闭云服务器", 4, "id", True, "String", "云服务器ID。", None),
        ("批量重启云服务器", 1, "reboot", True, "Object", "标记为重启云服务器操作，详情请参见表3。", 3),
        ("批量重启云服务器", 3, "type", True, "String", "重启类型：SOFT：普通重启。HARD：强制重启。", None),
        ("批量重启云服务器", 3, "servers", True, "Array of objects", "云服务器ID列表，详情请参见表4。", 4),
        ("批量重启云服务器", 4, "id", True, "String", "云服务器ID。", None),
        ("创建子网", 1, "subnet", True, "subnet object", "subnet对象，见表3", 3),
        ("创建子网", 3, "name", True, "String", "功能说明：子网名称 取值范围：1-64个字符，支持数字、字母、中文、_(下划线)、-（中划线）、.（点）", None),
        ("创建子网", 3, "description", False, "String", "功能说明：子网描述 取值范围：0-255个字符，不能包含“<”和“>”。", None),
        ("创建子网", 3, "cidr", True, "String", "功能说明：子网的网段 取值范围：必须在vpc对应cidr范围内 约束：必须是cidr格式。掩码长度不能大于28", None),
        ("创建子网", 3, "gateway_ip", True, "String", "功能说明：子网的网关 取值范围：子网网段中的IP地址 约束：必须是ip格式", None),
        ("创建子网", 3, "ipv6_enable", False, "Boolean", "功能说明：是否创建IPv6子网 取值范围：true（开启），false（关闭） 约束：不填时默认为false", None),
        ("创建子网", 3, "dhcp_enable", False, "Boolean", "功能说明：子网是否开启dhcp功能 取值范围：true（开启），false（关闭） 约束：不填时默认为true。当设置为false时，会导致新创建的ECS无法获取IP地址，Cloud-init无法注入帐号密码，请谨慎操作。", None),
        ("创建子网", 3, "primary_dns", False, "String", "功能说明：子网dns服务器地址1 约束：ip格式，不支持IPv6地址。不填时，默认为空 内网DNS地址请参见华为云提供的内网DNS地址是多少？ 可以通过查询名称服务器列表查看DNS服务器的地址。", None),
        ("创建子网", 3, "secondary_dns", False, "String", "功能说明：子网dns服务器地址2 约束：ip格式，不支持IPv6地址。不填时，默认为空。若只填secondary_dns，不填primary_dns，会自动把值填入primary_dns。 只有一个dns服务器地址时，只显示primary_dns，不显示secondary_dns。 内网DNS地址请参见华为云提供的内网DNS地址是多少？ 可以通过查询名称服务器列表查看DNS服务器的地址。", None),
        ("创建子网", 3, "dnsList", False, "Array of strings", "功能说明：子网dns服务器地址的集合；如果想使用两个以上dns服务器，请使用该字段 约束：是子网dns服务器地址1跟子网dns服务器地址2的合集的父集，不支持IPv6地址。不填时，默认为空 内网DNS地址请参见华为云提供的内网DNS地址是多少？ 可以通过查询名称服务器列表查看DNS服务器的地址。", None),
        ("创建子网", 3, "availability_zone", False, "String", "功能说明：子网所在的可用区标识，从终端节点获取，参考终端节点（Endpoint） 约束：系统存在的可用区标识；不填时，默认为空", None),
        ("创建子网", 3, "vpc_id", True, "String", "子网所在VPC标识", None),
        ("创建子网", 3, "extra_dhcp_opts", False, "Array of extra_dhcp_opt objects", "子网配置的NTP地址或租约时间，详情请参见extra_dhcp_opt对象（表4）。", 4),
        ("创建子网", 3, "tags", False, "Array of Strings", "功能说明：子网资源标签。创建子网时，给子网添加资源标签。 取值范围：最大10个标签 key：标签名称。不能为空，长度不超过128个字符(当前控制台操作key长度不超过36个字符)，由英文字母、数字、下划线、中划线、中文字符组成，同一资源的key值不能重复。 value：标签值。长度不超过255个字符(当前控制台操作value长度不超过43个字符)，由英文字母、数字、下划线、点、中划线、中文字符组成。 格式：[key*value]，每一个标签的key和value之间用*连接", None),
        ("创建子网", 4, "opt_value", False, "String", "功能说明：子网配置的NTP地址、DNS域名或租约到期时间。 约束： opt_name配置为“ntp”，则表示是子网ntp地址，目前只支持IPv4地址，每个IP地址以逗号隔开，IP地址个数不能超过4个，不能存在相同地址。该字段为null表示取消该子网NTP的设置，不能为“ ”(空字符串)。 opt_name配置为“domainname”，则该值表示是DNS配置的域名，用于向DNS服务器获取IP地址。域名只能由字母，数字，中划线组成，中划线不能在开头或末尾。域名至少包含两个字符串，单个字符串不超过63个字符，字符串间以点分隔。域名长度不超过254个字符。 opt_name配置为“addresstime”，则该值表示是子网租约到期时间，取值格式有两种，取-1，表示无限租约；数字+h，数字范围是1~30000，比如5h，默认值为24h。", None),
        ("创建子网", 4, "opt_name", True, "String", "功能说明：子网配置的NTP地址、DNS域名或租约到期时间的名称。 约束：目前只支持填写字符串“ntp”、\"domainname\"或“addresstime”。", None),
        ("创建VPC", 1, "vpc", True, "vpc object", "vpc对象，见表3", 3),
        ("创建VPC", 3, "name", False, "String", "功能说明：虚拟私有云名称 取值范围：0-64个字符，支持数字、字母、中文字符、_(下划线)、-（中划线）、.（点） 约束：如果名称不为空，则同一个租户下的名称不能重复", None),
        ("创建VPC", 3, "description", False, "String", "功能说明：虚拟私有云的描述 取值范围：0-255个字符，不能包含“<”和“>”。", None),
        ("创建VPC", 3, "cidr", False, "String", "功能说明：虚拟私有云下可用子网的范围 取值范围： 10.0.0.0/8~24 172.16.0.0/12~24 192.168.0.0/16~24 不指定cidr时，默认值为空 约束：必须是cidr格式，例如:192.168.0.0/16", None),
        ("创建VPC", 3, "enterprise_project_id", False, "String", "功能说明：企业项目ID。创建虚拟私有云时，给虚拟私有云绑定企业项目ID。 取值范围：最大长度36字节，带“-”连字符的UUID格式，或者是字符串“0”。“0”表示默认企业项目。  说明： 关于企业项目ID的获取及企业项目特性的详细信息，请参见《企业管理用户指南》。", None),
        ("创建VPC", 3, "tags", False, "Array of Strings", "功能说明：虚拟私有云资源标签。创建虚拟私有云时，给虚拟私有云添加资源标签。 取值范围：最大10个标签 key：标签名称。不能为空，长度不超过128个字符(当前控制台操作key长度不超过36个字符)，由英文字母、数字、下划 线、中划线、中文字符组成，同一资源的key值不能重复。 value：标签值。长度不超过255个字符(当前控制台操作value长度不超过43个字符)，由英文字母、数字、下划线、点、中划线、中文字符组成。 格式：[key*value]，每一个标签的key和value之间用*连接", None),
        ("地域推荐", 1, "flavor_constraint", False, "Object", "资源供给规格的约束，给出规格列表时优先使用规格列表，详情请参见表3。", 3),
        ("地域推荐", 1, "flavor_ids", False, "Array of strings", "接受推荐的规格列表。", None),
        ("地域推荐", 1, "locations", False, "Array of objects", "接受推荐的地域列表，默认接受所有区域。见表8", 8),
        ("地域推荐", 1, "option", False, "Object", "供给推荐的选项。见表9", 9),
        ("地域推荐", 1, "strategy", False, "String", "推荐的策略。 CAPACITY：容量策略 COST：成本策略", None),
        ("地域推荐", 1, "limit", False, "Integer", "查询返回的数量限制。", None),
        ("地域推荐", 1, "marker", False, "String", "取值为上一页数据的最后一条记录的唯一标记。", None),
        ("地域推荐", 3, "architecture_type", False, "Array of strings", "接受的体系结构描述。", None),
        ("地域推荐", 3, "flavor_requirements", False, "Array of objects", "资源的需求约束，详情请参见表4。", 4),
        ("地域推荐", 4, "vcpu_count", False, "Object", "规格的vCPU数量范围，不填表示接受所有，详情请参见表5。", 5),
        ("地域推荐", 4, "memory_mb", False, "Object", "规格的内存大小范围，不填表示接受所有，单位MiB，详情请参见表6。", 6),
        ("地域推荐", 4, "cpu_manufacturers", False, "Array of strings", "可选CPU制造商，不填表示接受所有。", None),
        ("地域推荐", 4, "memory_gb_per_vcpu", False, "Object", "规格的单vCPU对应内存容量范围，不填表示接受所有，内存单位GiB，详情请参见表7。", 7),
        ("地域推荐", 4, "instance_generations", False, "Array of strings", "接受的资源代系，不填表示接受所有。", None),
        ("地域推荐", 5, "max", False, "Integer", "最大值，-1表示无限制。", None),
        ("地域推荐", 5, "min", False, "Integer", "最小值，-1表示无限制。", None),
        ("地域推荐", 6, "max", False, "Integer", "最大值，-1表示无限制。", None),
        ("地域推荐", 6, "min", False, "Integer", "最小值，-1表示无限制。", None),
        ("地域推荐", 7, "max", False, "Double", "最大值，-1表示无限制。", None),
        ("地域推荐", 7, "min", False, "Double", "最小值，-1表示无限制。", None),
        ("地域推荐", 8, "region_id", False, "String", "区域ID。", None),
        ("地域推荐", 8, "availability_zone_id", False, "String", "可用区ID。", None),
        ("地域推荐", 9, "result_granularity", False, "String", "推荐结果的粒度。 BY_REGION：对每个区域打分，可使用多种规格满足需求。 BY_AZ：对每个可用区打分。 BY_FLAVOR：对每个规格打分，可使用多地域满足需求。 BY_FLAVOR_AND_REGION：对每个区域下的每个规格打分。 BY_FLAVOR_AND_AZ：对每个可用区下的每个规格打分。", None),
        ("地域推荐", 9, "enable_spot", False, "Boolean", "是否推荐竞价实例。", None),
        ("创建安全组", 1, "security_group", True, "security_group object", "安全组对象，请参见表3。", 3),
        ("创建安全组", 3, "name", True, "String", "功能说明：安全组名称。 取值范围：1-64个字符，支持数字、字母、中文字符、_(下划线)、-（中划线）、.（点）。", None),
        ("创建安全组", 3, "vpc_id", False, "String", "安全组所在的vpc的资源标识。 说明： 当前该参数只作提示用，不约束安全组在此vpc下，不建议继续使用。", None),
        ("创建安全组", 3, "enterprise_project_id", False, "String", "功能说明：企业项目ID。创建安全组时，给安全组绑定企业项目ID。 取值范围：最大长度36字节，带“-”连字符的UUID格式，或者是字符串“0”。“0”表示默认企业项目。 说明： 关于企业项目ID的获取及企业项目特性的详细信息，请参见《企业管理用户指南》。", None),
        ('创建集群', 3, 'apiVersion', True, 'String', '**参数解释：**\nAPI版本。\n**约束限制：**\n该值不可修改\n**取值范围：**\n- v3\n**默认取值：**\n不涉及', None),
        ('创建集群', 3, 'kind', True, 'String', '**参数解释：**\nAPI类型。\n**约束限制：**\n该值不可修改\n**取值范围：**\n- Cluster\n- cluster\n**默认取值：**\n不涉及', None),
        ('创建集群', 3, 'metadata', True, 'ClusterMetadata object', '**参数解释：**\n集群的基本信息，为集合类的元素类型，包含一组由不同名称定义的属性。\n**约束限制：**\n不涉及\n\n详情请参见表4\n\n详情请参见表4', 4),
        ('创建集群', 3, 'spec', True, 'ClusterSpec object', '**参数解释：**\nspec是集合类的元素类型，您对需要管理的集群对象进行详细描述的主体部分都在spec中给出。CCE通过spec的描述来创建或更新对象。\n**约束限制：**\n不涉及\n\n详情请参见表5\n\n详情请参见表5', 5),
        ('创建集群', 4, 'alias', False, 'String', '**参数解释：**\n集群显示名，用于在 CCE 界面显示，该名称创建后可修改。显示名和其他集群的名称、显示名不可以重复。\n**约束限制：**\n在创建集群、更新集群请求体中，集群显示名alias未指定或取值为空，表示与集群名称name一致。在创建集群等响应体中，集群显示名alias未配置时将不返回。\n**取值范围：**\n以中文或英文字符开头，由数字、中文、英文字符、中划线（-）组成，长度范围 4-128位，且不能以中划线（-）开头和结尾。\n**默认取值：**\n不涉及', None),
        ('创建集群', 4, 'annotations', False, 'Map<String,String>', '**参数解释：**\n集群注解，由key/value组成：\n"annotations": {\n"key1" : "value1",\n"key2" : "value2"\n}\n**约束限制：**\n该字段不会被数据库保存，当前仅用于指定集群待安装插件。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及\n说明：\n- Annotations不用于标识和选择对象。Annotations中的元数据可以是small或large，structured或unstructured，并且可以包括标签不允许使用的字符。\n- 可通过加入"cluster.install.addons.external/install":"[{"addonTemplateName":"icagent"}]"的键值对在创建集群时安装ICAgent。', None),
        ('创建集群', 4, 'creationTimestamp', False, 'String', '**参数解释：**\n集群创建时间。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 4, 'labels', False, 'Map<String,String>', '**参数解释：**\n集群标签，key/value对格式。\n**约束限制：**\n该字段值由系统自动生成，用于升级时前端识别集群支持的特性开关，用户指定无效。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 4, 'name', True, 'String', '**参数解释：**\n集群名称。\n**约束限制：**\n不涉及\n**取值范围：**\n以小写字母开头，由小写字母、数字、中划线(-)组成，长度范围4-128位，且不能以中划线(-)结尾。\n**默认取值：**\n不涉及', None),
        ('创建集群', 4, 'timezone', False, 'String', '**参数解释：**\n集群时区。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 4, 'uid', False, 'String', '**参数解释：**\n集群ID，资源唯一标识。\n**约束限制：**\n创建成功后自动生成，填写无效。在创建包周期集群时，响应体不返回集群ID。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 4, 'updateTimestamp', False, 'String', '**参数解释：**\n集群更新时间。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 5, 'authentication', False, 'Authentication object', '**参数解释：**\n集群认证方式相关配置。\n**约束限制：**\n不涉及\n\n详情请参见表13', 13),
        ('创建集群', 5, 'az', False, 'String', '**参数解释：**\n可用区（仅查询返回字段）。\nCCE支持的可用区请参考地区和终端节点。\n**约束限制：**\n不涉及', None),
        ('创建集群', 5, 'billingMode', False, 'Integer', '**参数解释：**\n集群的计费方式。\n**约束限制：**\n不涉及\n**取值范围：**\n- 0: 按需计费\n- 1: 包周期\n**默认取值：**\n默认0。', None),
        ('创建集群', 5, 'category', False, 'String', '**参数解释：**\n集群类别。\n**约束限制：**\n不涉及\n**取值范围：**\n- CCE：CCE集群\nCCE集群支持虚拟机与裸金属服务器混合、GPU、NPU等异构节点的混合部署，基于高性能网络模型提供全方位、多场景、安全稳定的容器运行环境。\n- Turbo: CCE Turbo集群。\n全面基于云原生基础设施构建的云原生2.0的容器引擎服务，具备软硬协同、网络无损、安全可靠、调度智能的优势，为用户提供一站式、高性价比的全新容器服务体验。\n**默认取值：**\n容器网络参数设置非eni模式时，默认为CCE\n容器网络参数设置为eni模式时，默认为Turbo', None),
        ('创建集群', 5, 'clusterOps', False, 'ClusterOps object', '**参数解释：**\n集群运维相关配置。\n**约束限制：**\n不涉及\n\n详情请参见表20', 20),
        ('创建集群', 5, 'clusterTags', False, 'Array of ResourceTag objects', '**参数解释：**\n集群资源标签。\n**约束限制：**\n不涉及\n\n详情请参见表16', 16),
        ('创建集群', 5, 'configurationsOverride', False, 'Array of PackageConfiguration objects', '**参数解释：**\n覆盖集群默认组件配置。\n当前支持的可配置组件及其参数详见配置管理。\n**约束限制：**\n若指定了不支持的组件或组件不支持的参数，该配置项将被忽略。\n\n详情请参见表18', 18),
        ('创建集群', 5, 'containerNetwork', True, 'ContainerNetwork object', '**参数解释：**\n容器网络参数，包含了容器网络类型和容器网段的信息。\n**约束限制：**\n不涉及\n\n详情请参见表7', 7),
        ('创建集群', 5, 'customSan', False, 'Array of strings', '**参数解释：**\n集群的API Server服务端证书中的自定义SAN（Subject Alternative Name）字段，遵从SSL标准X509定义的格式规范。\n**约束限制：**\n不允许出现同名重复。\n**取值范围：**\n格式符合IP和域名格式。\n**默认取值：**\n不涉及\n示例:\nSAN 1: DNS Name=example.com\nSAN 2: DNS Name=www.example.com\nSAN 3: DNS Name=example.net\nSAN 4: IP Address=93.184.216.34', None),
        ('创建集群', 5, 'deletionProtection', False, 'Boolean', '**参数解释：**\n集群删除保护，如果开启后用户将无法删除该集群。\n**约束限制：**\n不涉及。\n**取值范围：**\n- true: 开启集群删除保护\n- false: 关闭集群删除保护\n**默认取值：**\n默认false', None),
        ('创建集群', 5, 'description', False, 'String', '**参数解释：**\n集群描述，对于集群使用目的的描述，可根据实际情况自定义，默认为空。集群创建成功后可通过接口更新指定的集群来做出修改，也可在CCE控制台中对应集群的“集群详情”下的“描述”处进行修改。\n**约束限制：**\n仅支持utf-8编码。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 5, 'enableAutopilot', False, 'Boolean', '**参数解释：**\n是否为Autopilot集群。\n**约束限制：**\n不涉及\n**取值范围：**\n- true: 创建Autopilot类型集群\n- false: 创建CCE/Turbo类型集群\n**默认取值：**\n默认false', None),
        ('创建集群', 5, 'enableDistMgt', False, 'Boolean', '**参数解释：**\n集群开启对分布式云支持。\n**约束限制：**\n目前只有Turbo集群支持。\n**取值范围：**\n- true: 开启对分布式云支持\n- false: 关闭对分布式云支持\n**默认取值：**\n默认false', None),
        ('创建集群', 5, 'encryptionConfig', False, 'EncryptionConfig object', '**参数解释** ：\nsecret资源落盘加密配置，当前仅支持配置一种加密方式。默认使用cce托管密钥（用户侧不感知该密钥）进行加密。\n**约束限制** ：\n不涉及\n**取值范围** ：\n不涉及\n**默认取值** ：\n不涉及\n\n详情请参见表22', 22),
        ('创建集群', 5, 'eniNetwork', False, 'EniNetwork object', '**参数解释：**\n云原生网络2.0网络配置，创建CCE Turbo集群时指定。\n**约束限制：**\n不涉及\n\n详情请参见表9', 9),
        ('创建集群', 5, 'extendParam', False, 'ClusterExtendParam object', '**参数解释：**\n集群扩展字段，可配置多可用区集群、专属CCE集群，以及将集群创建在特定的企业项目下等。\n**约束限制：**\n不涉及\n\n详情请参见表17', 17),
        ('创建集群', 5, 'flavor', True, 'String', '**参数解释：**\n集群规格，当集群为v1.15及以上版本时支持创建后变更，详情请参见变更集群规格。请按实际业务需求进行选择\n**约束限制：**\n不涉及\n**取值范围：**\n- cce.s1.small: 小规模单控制节点CCE集群（最大50节点）\n- cce.s1.medium: 中等规模单控制节点CCE集群（最大200节点）\n- cce.s2.small: 小规模三控制节点CCE集群（最大50节点）\n- cce.s2.medium: 中等规模三控制节点CCE集群（最大200节点）\n- cce.s2.large: 大规模三控制节点CCE集群（最大1000节点）\n- cce.s2.xlarge: 超大规模三控制节点CCE集群（最大2000节点）\n**默认取值：**\n不涉及\n说明：\n关于规格参数中的字段说明如下：\n- s1：单控制节点的集群，控制节点数为1。单控制节点故障后，集群将不可用，但已运行工作负载不受影响。\n- s2：三控制节点的集群，即高可用集群，控制节点数为3。当某个控制节点故障时，集群仍然可用。\n- dec：表示专属云的CCE集群规格。例如cce.dec.s1.small表示小规模单控制节点的专属云CCE集群（最大50节点）。\n- small：表示集群支持管理的最大节点规模为50节点。\n- medium：表示集群支持管理的最大节点规模为200节点。\n- large：表示集群支持管理的最大节点规模为1000节点。\n- xlarge：表示集群支持管理的最大节点规模为2000节点。', None),
        ('创建集群', 5, 'hostNetwork', True, 'HostNetwork object', '**参数解释：**\n节点网络参数，包含了虚拟私有云VPC和子网的ID信息，而VPC是集群内节点之间的通信依赖，所以是必选的参数集。\n**约束限制：**\n不涉及\n\n详情请参见表6', 6),
        ('创建集群', 5, 'ipv6enable', False, 'Boolean', '**参数解释：**\n集群是否使用IPv6模式，1.15版本及以上支持。\n**约束限制：**\n开启IPv6后不支持iptables转发模式；VPC网络模式不支持IPv4/IPv6双栈网络。\n**取值范围：**\n- true: 开启IPv4/IPv6双栈模式\n- false: 仅使用IPv4模式\n**默认取值：**\nfalse', None),
        ('创建集群', 5, 'kubeProxyMode', False, 'String', '**参数解释：**\n服务转发模式。\n**约束限制：**\n不涉及\n**取值范围：**\n- iptables：社区传统的kube-proxy模式，完全以iptables规则的方式来实现service负载均衡。该方式最主要的问题是在服务多的时候产生太多的iptables规则，非增量式更新会引入一定的时延，大规模情况下有明显的性能问题。\n- ipvs：主导开发并在社区获得广泛支持的kube-proxy模式，采用增量式更新，吞吐更高，速度更快，并可以保证service更新期间连接保持不断开，适用于大规模场景。\n**默认取值：**\n默认使用iptables转发模式。', None),
        ('创建集群', 5, 'kubernetesSvcIpRange', False, 'String', '**参数解释：**\n服务网段参数，kubernetes clusterIP取值范围，1.11.7版本及以上支持。创建集群时如若未传参，默认为"10.247.0.0/16"。该参数废弃中，推荐使用新字段serviceNetwork，包含IPv4服务网段。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 5, 'legacyVersion', False, 'String', '**参数解释：**\nCCE集群旧版本（已废弃），无实际功能，仅用于集群version与platformVersion组合展示，该版本号全局内唯一。如集群version为va.b, platformVersion为cce.X.Y，则legacyVersion值为va.b.X-rY。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 5, 'masters', False, 'Array of MasterSpec objects', '**参数解释：**\n控制节点的高级配置。\n**约束限制：**\n该参数未配置时将不返回。\n\n详情请参见表15', 15),
        ('创建集群', 5, 'platformVersion', False, 'String', '**参数解释：**\nCCE集群平台版本号，表示集群版本(version)下的内部版本。用于跟踪某一集群版本内的迭代，集群版本内唯一，跨集群版本重新计数。\n**约束限制：**\n不支持用户指定，集群创建时自动选择对应集群版本的最新平台版本。\n**取值范围：**\nplatformVersion格式为：cce.X.Y\n- X: 表示内部特性版本。集群版本中特性或者补丁修复，或者OS支持等变更场景。其值从1开始单调递增。\n- Y: 表示内部特性版本的补丁版本。仅用于特性版本上线后的软件包更新，不涉及其他修改。其值从0开始单调递增。\n**默认取值：**\n不涉及', None),
        ('创建集群', 5, 'publicAccess', False, 'PublicAccess object', '**参数解释：**\n集群API访问控制。\n**约束限制：**\n不涉及\n\n详情请参见表12', 12),
        ('创建集群', 5, 'serviceNetwork', False, 'ServiceNetwork object', '**参数解释：**\n服务网段参数，包含IPv4 CIDR。\n**约束限制：**\n不涉及\n\n详情请参见表11', 11),
        ('创建集群', 5, 'supportIstio', False, 'Boolean', '**参数解释：**\n支持Istio。\n**约束限制：**\n不涉及\n**取值范围：**\n- true: 支持istio\n- false: 不支持istio\n**默认取值：**\n默认true', None),
        ('创建集群', 5, 'type', False, 'String', '**参数解释：**\n集群Master节点架构\n**约束限制：**\n不涉及\n**取值范围：**\n- VirtualMachine：Master节点为x86架构服务器\n- ARM64: Master节点为鲲鹏（ARM架构）服务器\n**默认取值：**\nVirtualMachine', None),
        ('创建集群', 5, 'version', False, 'String', '**参数解释：**\n集群版本，与Kubernetes社区基线版本保持一致，建议选择最新版本。\n在CCE控制台支持创建三种最新版本的集群。可登录CCE控制台创建集群，在“版本”处获取到集群版本。\n其它集群版本，当前仍可通过api创建，但后续会逐渐下线，具体下线策略请关注CCE官方公告。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n- 若不配置，默认创建最新版本的集群。\n- 若指定集群基线版本但是不指定具体r版本，则系统默认选择对应集群版本的最新r版本。建议不指定具体r版本由系统选择最新版本。\n说明：\n- Turbo集群支持1.19及以上版本商用。', None),
        ('创建集群', 6, 'SecurityGroup', False, 'String', '**参数解释：**\n集群默认的Node节点安全组ID。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n- 不指定该字段系统将自动为用户创建默认Node节点安全组。\n- 指定该字段时集群将绑定指定的安全组。\n说明：\n指定Node节点安全组需要放通部分端口来保证正常通信。详细设置请参考集群安全组规则配置。', None),
        ('创建集群', 6, 'controlPlaneSecurityGroup', False, 'String', '**参数解释：**\n集群控制面节点安全组ID。\n**约束限制：**\n创建成功后自动生成，填写无效。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 6, 'subnet', True, 'String', '**参数解释：**\n用于创建控制节点的subnet的网络ID。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及\n获取方法如下：\n- 方法1：登录虚拟私有云服务的控制台界面，单击VPC下的子网，进入子网详情页面，查找网络ID。\n- 方法2：通过虚拟私有云服务的查询子网列表接口查询。\n链接请参见查询子网列表。', None),
        ('创建集群', 6, 'vpc', True, 'String', '**参数解释：**\n用于创建控制节点的VPC的ID。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及\n获取方法如下：\n- 方法1：登录虚拟私有云服务的控制台界面，在虚拟私有云的详情页面查找VPC ID。\n- 方法2：通过虚拟私有云服务的API接口查询。\n链接请参见查询VPC列表。', None),
        ('创建集群', 7, 'cidr', False, 'String', '**参数解释：**\n容器网络网段，建议使用网段10.0.0.0/12~19，172.16.0.0/16~19，192.168.0.0/16~19，如存在网段冲突，将会报错。\n**约束限制：**\n此参数在集群创建后不可更改，请谨慎选择。（已废弃，如填写cidrs将忽略该cidr）\nvpc网络模式的集群在创建后可以新增网段参数，不可修改已有网段参数，需要重新创建集群才能调整。\n**取值范围：**\n满足IPv4 CIDR格式\n**默认取值：**\n不填此参数时，将从172.(16 ~ 31).0.0/16、10.(0 | 16 | 32 | 48 | 64 | 80 | 96 | 112).0.0/12中随机分配一个不冲突的网段供用户使用。', None),
        ('创建集群', 7, 'cidrs', False, 'Array of ContainerCIDR objects', '**参数解释：**\n容器网络网段列表。1.21及新版本集群使用cidrs字段，当集群网络类型为vpc-router类型时，支持多个容器网段，最多配置20个；1.21之前版本若使用cidrs字段，则取值cidrs数组中的第一个cidr元素作为容器网络网段地址。\n**约束限制：**\n容器隧道网络模式的集群在创建之后，无法修改网段参数；\nvpc网络模式的集群在创建后可以新增网段参数，不可修改已有网段参数，需要重新创建集群才能调整。\n\n详情请参见表8', 8),
        ('创建集群', 7, 'mode', True, 'String', '**参数解释：**\n容器网络类型。\n**约束限制：**\n只可选择一个容器网络类型。\n**取值范围：**\n- overlay_l2：容器隧道网络，通过OVS（OpenVSwitch）为容器构建的overlay_l2网络。\n- vpc-router：VPC网络，使用ipvlan和自定义VPC路由为容器构建的Underlay的l2网络。\n- eni：云原生网络2.0，深度整合VPC原生ENI弹性网卡能力，采用VPC网段分配容器地址，支持ELB直通容器，享有高性能，创建CCE Turbo集群时指定。\n**默认取值：**\n不涉及', None),
        ('创建集群', 8, 'cidr', True, 'String', '**参数解释：**\n容器网络网段，建议使用网段10.0.0.0/12~19，172.16.0.0/16~19，192.168.0.0/16~19。\n**约束限制：**\n如存在网段冲突，将会报错。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 9, 'eniSubnetCIDR', False, 'String', '**参数解释：**\nENI子网CIDR。\n**约束限制：**\n废弃中，推荐使用新字段subnets。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 9, 'eniSubnetId', True, 'String', '**参数解释：**\nENI所在子网的IPv4子网ID。\n**约束限制：**\n暂不支持IPv6,废弃中，推荐使用新字段subnets。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及\n获取方法如下：\n- 方法1：登录虚拟私有云服务的控制台界面，单击VPC下的子网，进入子网详情页面，查找IPv4子网ID。\n- 方法2：通过虚拟私有云服务的查询子网列表接口查询。\n链接请参见查询子网列表。', None),
        ('创建集群', 9, 'subnets', True, 'Array of NetworkSubnet objects', '**参数解释：**\nIPv4子网ID列表。\n**约束限制：**\n不涉及\n\n详情请参见表10', 10),
        ('创建集群', 10, 'subnetID', True, 'String', '**参数解释：**\n用于创建控制节点的subnet的IPv4子网ID。\n**约束限制：**\n暂不支持IPv6\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及\n获取方法如下：\n- 方法1：登录虚拟私有云服务的控制台界面，单击VPC下的子网，进入子网详情页面，查找IPv4子网ID。\n- 方法2：通过虚拟私有云服务的查询子网列表接口查询。\n链接请参见查询子网列表。', None),
        ('创建集群', 11, 'IPv4CIDR', False, 'String', '**参数解释：**\nkubernetes clusterIP IPv4 CIDR取值范围。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n默认为"10.247.0.0/16"。', None),
        ('创建集群', 11, 'IPv6CIDR', False, 'String', '**参数解释：**\nkubernetes clusterIP IPv6 CIDR取值范围。\n**约束限制：**\n仅开启IPV6双栈的Turbo集群支持配置IPv6服务网段。\n**取值范围：**\n不涉及\n**默认取值：**\nTurbo集群默认为"fc00::/112"\nCCE集群默认为"fd00:1234::/120"', None),
        ('创建集群', 12, 'cidrs', False, 'Array of strings', '**参数解释：**\n允许访问集群API的白名单网段列表，建议对VPC网段、容器网段放通。\n**约束限制：**\n该字段仅支持创建集群时传入，更新时指定无效\n**取值范围：**\n不涉及\n**默认取值：**\n默认无白名单配置，为["0.0.0.0/0"]。', None),
        ('创建集群', 13, 'authenticatingProxy', False, 'AuthenticatingProxy object', '**参数解释：**\nauthenticatingProxy模式相关配置。\n**约束限制：**\n认证模式为authenticating_proxy时必选。\n\n详情请参见表14', 14),
        ('创建集群', 13, 'mode', False, 'String', '**参数解释：**\n集群认证模式。\n**约束限制：**\n不涉及\n**取值范围：**\n- kubernetes 1.11及之前版本的集群支持“x509”、“rbac”和“authenticating_proxy”，默认取值为“x509”。\n- kubernetes 1.13及以上版本的集群支持“rbac”和“authenticating_proxy”，默认取值为“rbac”。\n**默认取值：**\n- kubernetes 1.11及之前版本的集群默认取值为“x509”。\n- kubernetes 1.13及以上版本的集群默认取值为“rbac”。', None),
        ('创建集群', 14, 'ca', False, 'String', '**参数解释：**\nauthenticating_proxy模式配置的x509格式CA证书(base64编码)。\n**约束限制：**\n当集群认证模式为authenticating_proxy时，此项必须填写。\n**取值范围：**\n最大长度：1M。\n**默认取值：**\n不涉及', None),
        ('创建集群', 14, 'cert', False, 'String', '**参数解释：**\nauthenticating_proxy模式配置的x509格式CA证书签发的客户端证书，用于kube-apiserver到扩展apiserver的认证。(base64编码)。\n**约束限制：**\n当集群认证模式为authenticating_proxy时，此项必须填写。\n**取值范围：**\n最大长度：1M。\n**默认取值：**\n不涉及', None),
        ('创建集群', 14, 'privateKey', False, 'String', '**参数解释：**\nauthenticating_proxy模式配置的x509格式CA证书签发的客户端证书时对应的私钥，用于kube-apiserver到扩展apiserver的认证。Kubernetes集群使用的私钥尚不支持密码加密，请使用未加密的私钥。(base64编码)。\n**约束限制：**\n当集群认证模式为authenticating_proxy时，此项必须填写。\n**取值范围：**\n最大长度：1M。\n**默认取值：**\n不涉及', None),
        ('创建集群', 15, 'availabilityZone', False, 'String', '**参数解释：**\n可用区。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 16, 'key', False, 'String', '**参数解释：**\nKey值。\n**约束限制：**\n不涉及\n**取值范围：**\n- 不能为空且首尾不能包含空格，最多支持128个字符\n- 可用UTF-8格式表示的汉字、字母、数字和空格\n- 支持部分特殊字符：_.:=+-@\n- 不能以"_sys_"开头\n**默认取值：**\n不涉及', None),
        ('创建集群', 16, 'value', False, 'String', '**参数解释：**\nValue值。\n**约束限制：**\n不涉及\n**取值范围：**\n- 可以为空但不能缺省，最多支持255个字符\n- 可用UTF-8格式表示的汉字、字母、数字和空格\n- 支持部分特殊字符：_.:/=+-@\n**默认取值：**\n不涉及', None),
        ('创建集群', 17, 'alpha.cce/fixPoolMask', False, 'String', '**参数解释：**\n容器网络固定IP池掩码位数，该参数决定节点可分配容器IP数量，与创建节点时设置的maxPods参数共同决定节点最多可以创建多少个Pod，\n具体请参见节点可创建的最大Pod数量说明。\n**约束限制：**\n仅vpc-router网络支持。\n**取值范围：**\n整数字符串取值范围: 24 ~ 28\n**默认取值：**\n默认值24', None),
        ('创建集群', 17, 'clusterAZ', False, 'String', '**参数解释：**\n集群控制节点可用区配置。\nCCE支持的可用区请参考地区和终端节点。\n**约束限制：**\n不涉及\n**取值范围：**\n- 指定局点支持可用区。\n- multi_az：多可用区，可选。仅使用多控制节点集群时才可以配置多可用区。\n- 专属云计算池可用区：用于指定专属云可用区部署集群控制节点。如果需配置专属CCE集群，该字段为必选。\n**默认取值：**\n不指定默认随机分配可用区。', None),
        ('创建集群', 17, 'clusterExternalIP', False, 'String', '**参数解释：**\nmaster 弹性公网IP\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 17, 'decMasterFlavor', False, 'String', '**参数解释：**\n专属CCE集群指定可控制节点的规格。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 17, 'dockerUmaskMode', False, 'String', '**参数解释：**\n集群默认Docker的UmaskMode配置。\n**约束限制：**\n不涉及\n**取值范围：**\n- secure\n- normal\n**默认取值：**\n默认normal', None),
        ('创建集群', 17, 'dssMasterVolumes', False, 'String', '**参数解释：**\n用于指定控制节点的系统盘和数据盘使用专属分布式存储，未指定或者值为空时，默认使用EVS云硬盘。\n**约束限制：**\n如果配置专属CCE集群，该字段为必选，请按照如下格式设置：\n<rootVol.dssPoolID>.<rootVol.volType>;<dataVol.dssPoolID>.<dataVol.volType>\n字段说明：\n- rootVol为系统盘；dataVol为数据盘；\n- dssPoolID为专属分布式存储池ID；\n- volType为专属分布式存储池的存储类型，如SAS、SSD、SATA、ESSD、GPSSD、ESSD2、GPSSD2\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及\n样例：c950ee97-587c-4f24-8a74-3367e3da570f.sas;6edbc2f4-1507-44f8-ac0d-eed1d2608d38.ssd\n说明：\n非专属CCE集群不支持配置该字段。', None),
        ('创建集群', 17, 'enterpriseProjectId', False, 'String', '**参数解释：**\n集群所属的企业项目ID。\n**约束限制：**\n需要开通企业项目功能后才可配置企业项目。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 17, 'isAutoPay', False, 'String', '**参数解释：**\n是否自动扣款。\n**约束限制：**\nbillingMode为1时生效。\n**取值范围：**\n- "true"：自动扣款\n- "false"：不自动扣款\n**默认取值：**\n默认false', None),
        ('创建集群', 17, 'isAutoRenew', False, 'String', '**参数解释：**\n是否自动续订\n**约束限制：**\nbillingMode为1时生效。\n**取值范围：**\n- "true"：自动续订\n- "false"：不自动续订\n**默认取值：**\n默认false', None),
        ('创建集群', 17, 'kubeProxyMode', False, 'String', '**参数解释：**\n服务转发模式，支持以下两种实现：\n**约束限制：**\n此参数已废弃，若同时指定此参数和ClusterSpec下的kubeProxyMode，以ClusterSpec下的为准。\n**取值范围：**\n- iptables：社区传统的kube-proxy模式，完全以iptables规则的方式来实现service负载均衡。该方式最主要的问题是在服务多的时候产生太多的iptables规则，非增量式更新会引入一定的时延，大规模情况下有明显的性能问题\n- ipvs：主导开发并在社区获得广泛支持的kube-proxy模式，采用增量式更新，吞吐更高，速度更快，并可以保证service更新期间连接保持不断开，适用于大规模场景。\n**默认取值：**\n默认iptables。', None),
        ('创建集群', 17, 'kubernetes.io/cpuManagerPolicy', False, 'String', '**参数解释：**\n集群CPU管理策略。\n**约束限制：**\n不涉及\n**取值范围：**\n- none(或空值)：关闭工作负载实例独占CPU核的功能，优点是CPU共享池的可分配核数较多\n- static：支持给节点上的工作负载实例配置CPU独占，适用于对CPU缓存和调度延迟敏感的工作负载，Turbo集群下仅对普通容器节点有效，安全容器节点无效。\n**默认取值：**\n默认none', None),
        ('创建集群', 17, 'orderID', False, 'String', '**参数解释：**\n订单ID。\n**约束限制：**\n集群付费类型为自动付费包周期类型时，响应中会返回此字段(仅创建场景涉及)。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 17, 'periodNum', False, 'Integer', '**参数解释：**\n订购周期数\n**约束限制：**\n作为请求参数，billingMode为1时生效，且为必选。\n作为响应参数，仅在创建包周期集群时返回。\n**取值范围：**\n- periodType=month（周期类型为月）时，取值为[1-9]。\n- periodType=year（周期类型为年）时，取值为[1-3]。\n**默认取值：**\n不涉及', None),
        ('创建集群', 17, 'periodType', False, 'String', '**参数解释：**\n订购周期单位。\n**约束限制：**\n作为请求参数，billingMode为1（包周期）时生效，且为必选。\n作为响应参数，仅在创建包周期集群时返回。\n**取值范围：**\n- month：月\n- year：年\n**默认取值：**\n不涉及', None),
        ('创建集群', 17, 'upgradefrom', False, 'String', '**参数解释：**\n记录集群通过何种升级方式升级到当前版本。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 18, 'configurations', False, 'Array of ConfigurationItem objects', '**参数解释：**\n组件配置项。\n**约束限制：**\n不涉及\n\n详情请参见表19', 19),
        ('创建集群', 18, 'name', False, 'String', '**参数解释：**\n组件名称。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 19, 'name', False, 'String', '**参数解释：**\n覆盖集群默认组件配置。\n当前支持的可配置组件及其参数详见配置管理。\n**约束限制：**\n若指定了不支持的组件或组件不支持的参数，该配置项将被忽略。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 19, 'value', False, 'AnyType', '**参数解释：**\n覆盖集群默认组件配置。\n当前支持的可配置组件及其参数详见配置管理。\n**约束限制：**\n若指定了不支持的组件或组件不支持的参数，该配置项将被忽略。\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 20, 'alarm', True, 'AlarmInfo object', '**参数解释：**\n告警助手参数配置。基于AOM服务的告警能力实现，提供集群内的告警快速检索、告警快速配置的能力，告警中心的指标类告警规则依赖云原生监控插件上报数据到AOM实例。\n**约束限制：**\n不涉及\n\n详情请参见表21', 21),
        ('创建集群', 21, 'alarmRuleTemplateId', False, 'String', '**参数解释：**\n开启告警助手时传入告警模板ID。默认采用容器场景下的告警规则模板。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 21, 'promEnterpriseProjectID', False, 'String', '**参数解释：**\n开启告警助手时传入AOM普罗实例的企业项目id。若未安装普罗插件或者未对接AOM实例，此参数无需指定，告警中心将不会创建指标类告警规则。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 21, 'promInstanceID', False, 'String', '**参数解释：**\n开启告警助手时传入AOM普罗实例的id。若未安装普罗插件或者未对接AOM实例，此参数无需指定，告警中心将不会创建指标类告警规则。\n**约束限制：**\n不涉及\n**取值范围：**\n不涉及\n**默认取值：**\n不涉及', None),
        ('创建集群', 21, 'topics', True, 'Array of strings', '**参数解释：**\n联系组列表。填写SMN主题名称，通过配置告警联系组，分组管理订阅终端，接收告警信息。\n**约束限制：**\n不涉及', None),
        ('创建集群', 22, 'kmsKeyID', False, 'String', '**参数解释** ：\nkms密钥ID\n- 集群创建API中，如果mode字段设置为Default，无需填写该字段；如果mode字段设置为KMS，则支持填写该字段。若字段为空，则默认使用KMS默认密钥进行填充，默认密钥不存在时云服务将自动为用户创建cce/default默认密钥。 用户需使用真实存在的KMS密钥，并且在集群生命周期结束前，禁止删除、禁用密钥等操作，防止集群功能异常（集群设置该密钥后不允许修改）。\n- 集群查询API中，如果mode字段设置为Default，则该字段返回为空；若mode字段设置为KMS，则该字段为具体的密钥ID。\n**约束限制** ：\n不涉及\n**取值范围** ：\n不涉及\n**默认取值** ：\n不涉及', None),
        ('创建集群', 22, 'mode', False, 'String', '**参数解释** ：\n加密模式，可以配置为使用cce本地密钥加密或KMS加密。\n**约束限制** ：\n不涉及\n**取值范围** ：\n- Default：使用cce本地密钥加密\n- KMS：使用KMS加密模式\n**默认取值** ：\nDefault', None),
    ]

    cursor.executemany('''
        INSERT INTO apis (name, method, uri, description, root_table_id, doc_page)
        VALUES (?, ?, ?, ?, ?, ?)''', apis_data)
    
    def find_api_id_from_name (cursor: sqlite3.Cursor, api_name: str) -> int:
        # find apis.id from name
        cursor.execute('SELECT id FROM apis WHERE name = ?', (api_name,))
        api_rows = cursor.fetchall()
        assert len(api_rows) == 1, f"API '{api_name}' does not exist or has duplicates."
        api_id = api_rows[0][0]  # Extract the id from the fetched row
        return api_id

    for api_name, parameter, mandatory, type_, description in uri_parameters_data:
        api_id = find_api_id_from_name(cursor, api_name)
        cursor.execute('''
            INSERT INTO uri_parameters (api_id, parameter, mandatory, type, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (api_id, parameter, mandatory, type_, description))

    for api_name, table_id, parameter, mandatory, type_, description, ref_table_id in request_parameters_data:
        api_id = find_api_id_from_name(cursor, api_name)
        cursor.execute('''
            INSERT INTO request_parameters (api_id, table_id, parameter, mandatory, type, description, ref_table_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (api_id, table_id, parameter, mandatory, type_, description, ref_table_id))
    
    conn.commit()
    conn.close()
    return

def main():
    init_api_database()
    insert_data()
    return

if __name__ == "__main__":
    main()
