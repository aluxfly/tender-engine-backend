const fs = require('fs');
const path = require('path');

// 加载模板
function loadTemplate(templateType) {
  const templatePath = path.join(__dirname, '../templates', `${templateType}-template.json`);
  const templateData = fs.readFileSync(templatePath, 'utf8');
  return JSON.parse(templateData);
}

// 模板匹配逻辑
function matchTemplate(projectType) {
  const typeMap = {
    '物联网卡': 'iot-sim-card',
    'sim卡': 'iot-sim-card',
    'eSIM': 'iot-sim-card',
    'M2M卡': 'iot-sim-card',
    '布控球': 'surveillance-ball',
    '监控球': 'surveillance-ball',
    '视频监控': 'surveillance-ball'
  };
  
  return typeMap[projectType] || 'iot-sim-card';
}

// 生成标书内容
function generateBidContent(template, formData) {
  const content = {
    title: `投标文件 - ${formData.project_name || '未知项目'}`,
    project_info: {
      name: formData.project_name,
      code: formData.project_code,
      type: formData.project_type
    },
    company_info: {
      name: formData.company_info?.company_name,
      contact: {
        person: formData.company_info?.contact_person,
        phone: formData.company_info?.contact_phone,
        email: formData.company_info?.contact_email
      }
    },
    technical_spec: {},
    pricing: {
      unit_price: formData.pricing?.unit_price,
      total_price: formData.pricing?.total_price,
      payment_terms: formData.pricing?.payment_terms
    },
    qualifications: formData.qualifications || {},
    case_studies: formData.case_studies || {}
  };
  
  // 根据模板类型添加技术规格
  if (template.template_id === 'iot-sim-card') {
    content.technical_spec = {
      card_type: formData.sim_card_spec?.card_type,
      frequency_band: formData.sim_card_spec?.frequency_band,
      data_plan: formData.sim_card_spec?.data_plan,
      operator: formData.sim_card_spec?.operator,
      apn: formData.sim_card_spec?.apn,
      platform_type: formData.service_requirements?.platform_type,
      qos: formData.technical_spec?.qos,
      security: formData.technical_spec?.security
    };
  } else if (template.template_id === 'surveillance-ball') {
    content.technical_spec = {
      video_resolution: formData.device_spec?.video_resolution,
      frame_rate: formData.device_spec?.frame_rate,
      bit_rate: formData.device_spec?.bit_rate,
      storage: formData.device_spec?.storage,
      power: formData.device_spec?.power,
      installation: formData.device_spec?.installation,
      wireless: formData.network?.wireless,
      protocol: formData.network?.protocol
    };
  }
  
  return content;
}

// 导出函数
module.exports = {
  loadTemplate,
  matchTemplate,
  generateBidContent
};
